#!/usr/bin/env python3
"""
smart_proxy.py — Dual-Persona Swiss Geo-Masking & Multi-Exit Proxy Engine

Supports independent multi-channel routing for simultaneous / separated user sessions:
  Channel A (Persona A - Husband):
    HTTP  proxy : 0.0.0.0:8888  (CONNECT for HTTPS + HTTP header injection)
    SOCKS5 proxy: 0.0.0.0:1080  (TCP tunnel)
    Upstream    : Configured in personas.json / env
    Fingerprint : Swiss German de-CH + Persona A User-Agent

  Channel B (Persona B - Wife):
    HTTP  proxy : 0.0.0.0:8889  (CONNECT for HTTPS + HTTP header injection)
    SOCKS5 proxy: 0.0.0.0:1081  (TCP tunnel)
    Upstream    : Configured in personas.json / env
    Fingerprint : Swiss French/German fr-CH/de-CH + Persona B User-Agent
"""

import os
import sys
import json
import asyncio
import struct
import logging
import urllib.parse
import aiohttp
try:
    from aiohttp_socks import ProxyConnector
except ImportError:
    ProxyConnector = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger("smart_proxy")

BIND = os.getenv('BIND_ADDR', '0.0.0.0')
BUF = 65536
PERSONAS_FILE = os.getenv('PERSONAS_FILE', '/opt/watchdog/personas.json')

DEFAULT_PERSONAS = {
    "active_persona": "husband",
    "husband": {
        "name": "Чоловік (Persona A)",
        "exit_node": "100.100.74.9",
        "device_name": "tab-s8-ultra",
        "upstream": "direct",
        "http_port": 8888,
        "socks_port": 1080,
        "lang": "de-CH,de;q=0.9,en;q=0.8",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'
    },
    "wife": {
        "name": "Дружина (Persona B)",
        "exit_node": "100.87.198.99",
        "device_name": "oneplus-pad-go-2",
        "upstream": "socks5://100.87.198.99:9888",
        "http_port": 8889,
        "socks_port": 1081,
        "lang": "de-CH,de;q=0.9,fr-CH;q=0.8,en;q=0.7",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "sec_ch_ua": '"Firefox";v="126", "Gecko";v="20100101"'
    },
    "berveno": {
        "name": "Руслан Бервено (Persona C)",
        "exit_node": "100.87.198.99",
        "device_name": "oneplus-pad-go-2",
        "upstream": "direct",
        "http_port": 8890,
        "socks_port": 1082,
        "lang": "de-CH,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="133", "Google Chrome";v="133", "Not-A.Brand";v="99"'
    }
}


def load_personas():
    data = DEFAULT_PERSONAS.copy()
    if os.path.exists(PERSONAS_FILE):
        try:
            with open(PERSONAS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                data.update(loaded)
        except Exception as e:
            logger.warning(f"Failed to load {PERSONAS_FILE}: {e}")
    return data


STRIP_REQ = {
    'x-forwarded-for', 'x-real-ip', 'via', 'forwarded',
    'proxy-connection', 'proxy-authorization', 'cf-connecting-ip',
    'true-client-ip', 'x-client-ip', 'client-ip', 'x-cluster-client-ip'
}


def parse_upstream(upstream_str: str):
    """Parse upstream string into (type, host, port)."""
    if not upstream_str or upstream_str.strip().lower() == 'direct':
        return ('direct', None, None)
    parsed = urllib.parse.urlparse(upstream_str)
    if parsed.scheme.startswith('socks5'):
        return ('socks5', parsed.hostname, parsed.port or 1080)
    return ('direct', None, None)


# ── Upstream Connector ──────────────────────────────────────────────────────

async def open_outbound_connection(target_host: str, target_port: int, upstream_mode: tuple):
    """Connect to target_host:target_port either directly or via upstream SOCKS5."""
    mode, up_host, up_port = upstream_mode
    if mode == 'direct':
        return await asyncio.open_connection(target_host, target_port)

    if mode == 'socks5':
        last_exc = None
        r, w = None, None
        for attempt in range(1, 3):
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(up_host, up_port), timeout=8)
                break
            except Exception as e:
                last_exc = e
                logger.warning(f"Upstream SOCKS5 ({up_host}:{up_port}) attempt {attempt}/2 failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(0.5)

        if r is None or w is None:
            logger.error(f"[FAIL-CLOSED] Upstream SOCKS5 ({up_host}:{up_port}) unreachable after 2 attempts: {last_exc}. Rejecting connection without direct fallback.")
            raise ConnectionError(f"Fail-Closed: Upstream SOCKS5 ({up_host}:{up_port}) unreachable: {last_exc}")

        # SOCKS5 Handshake
        w.write(b'\x05\x01\x00')
        await w.drain()
        auth_resp = await r.readexactly(2)
        if auth_resp[1] != 0x00:
            w.close()
            raise ConnectionError('Upstream SOCKS5 auth failed')

        # SOCKS5 CONNECT
        hb = target_host.encode('utf-8')
        w.write(b'\x05\x01\x00\x03' + bytes([len(hb)]) + hb + struct.pack('!H', target_port))
        await w.drain()
        rep = await r.readexactly(4)
        if rep[1] != 0x00:
            w.close()
            raise ConnectionError(f'Upstream SOCKS5 connect failed with status {rep[1]}')

        atype = rep[3]
        if atype == 1:
            await r.readexactly(4)
        elif atype == 3:
            dlen = (await r.readexactly(1))[0]
            await r.readexactly(dlen)
        elif atype == 4:
            await r.readexactly(16)
        await r.readexactly(2)
        return r, w

    raise ValueError(f"Unknown upstream mode: {mode}")


# ── Bidirectional Pipe ───────────────────────────────────────────────────────

async def pipe(src, dst):
    try:
        while True:
            data = await src.read(BUF)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except Exception:
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


# ── Generic HTTP Proxy Handler ───────────────────────────────────────────────

class HttpProxyChannel:
    def __init__(self, channel_name: str, upstream_str: str, headers_builder):
        self.name = channel_name
        self.upstream = parse_upstream(upstream_str)
        self.headers_builder = headers_builder

    def get_current_headers(self):
        if callable(self.headers_builder):
            return self.headers_builder()
        return self.headers_builder

    async def handle_client(self, cr, cw):
        peer = cw.get_extra_info('peername', ('?', 0))[0]
        try:
            raw = b''
            while b'\r\n\r\n' not in raw:
                chunk = await asyncio.wait_for(cr.read(4096), timeout=15)
                if not chunk:
                    return
                raw += chunk
                if len(raw) > 16384:
                    break

            head, _, body_start = raw.partition(b'\r\n\r\n')
            lines = head.decode('utf-8', errors='replace').split('\r\n')
            req_line = lines[0]
            parts = req_line.split(' ', 2)
            if len(parts) < 2:
                return
            method, path = parts[0], parts[1]

            # ── CONNECT (HTTPS tunnel) ──────────────────────────────────────
            if method == 'CONNECT':
                host, _, port = path.rpartition(':')
                port = int(port or 443)
                logger.info(f"[{self.name}] CONNECT {host}:{port} from {peer}")
                try:
                    ur, uw = await open_outbound_connection(host, port, self.upstream)
                except Exception as e:
                    logger.warning(f"[{self.name}] CONNECT failed for {host}:{port} — {e}")
                    cw.write(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
                    await cw.drain()
                    return
                cw.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
                await cw.drain()
                await asyncio.gather(pipe(cr, uw), pipe(ur, cw))
                return

            # ── Plain HTTP ──────────────────────────────────────────────────
            req_headers = {}
            for ln in lines[1:]:
                if ':' in ln:
                    k, _, v = ln.partition(':')
                    req_headers[k.strip().lower()] = v.strip()

            host = req_headers.get('host', '')
            logger.info(f"[{self.name}] {method} {path[:70]} from {peer}")

            cur_headers = self.get_current_headers()
            fwd_headers = {k: v for k, v in req_headers.items() if k not in STRIP_REQ}
            fwd_headers.update({k.lower(): v for k, v in cur_headers.items()})

            body = body_start
            clen = int(req_headers.get('content-length', 0))
            while len(body) < clen:
                body += await cr.read(clen - len(body))

            connector = None
            if self.upstream[0] == 'socks5' and ProxyConnector is not None:
                connector = ProxyConnector.from_url(f'socks5://{self.upstream[1]}:{self.upstream[2]}', ssl=False)

            try:
                async with aiohttp.ClientSession(connector=connector) as session:
                    async with session.request(
                        method=method,
                        url=path if path.startswith('http') else f'http://{host}{path}',
                        headers=fwd_headers,
                        data=body or None,
                        allow_redirects=False,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        rb = await resp.read()
                        status_line = f'HTTP/1.1 {resp.status} {resp.reason}\r\n'
                        resp_hdrs = ''.join(
                            f'{k}: {v}\r\n'
                            for k, v in resp.headers.items()
                            if k.lower() not in {'transfer-encoding'}
                        )
                        cw.write(status_line.encode() + resp_hdrs.encode() + b'\r\n' + rb)
                        await cw.drain()
            except Exception as e:
                logger.warning(f"[{self.name}] HTTP forward error: {e}")
                cw.write(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
                await cw.drain()

        except Exception as e:
            logger.debug(f"[{self.name}] http_proxy error: {e}")
        finally:
            try:
                cw.close()
            except Exception:
                pass


# ── Generic SOCKS5 Proxy Handler ─────────────────────────────────────────────

class Socks5ProxyChannel:
    def __init__(self, channel_name: str, upstream_str: str):
        self.name = channel_name
        self.upstream = parse_upstream(upstream_str)

    async def handle_client(self, cr, cw):
        peer = cw.get_extra_info('peername', ('?', 0))[0]
        try:
            g = await cr.readexactly(2)
            if g[0] != 0x05:
                return
            await cr.readexactly(g[1])
            cw.write(b'\x05\x00')
            await cw.drain()

            req = await cr.readexactly(4)
            if req[1] != 0x01:
                cw.write(b'\x05\x07\x00\x01' + b'\x00'*6)
                return

            atype = req[3]
            if atype == 0x01:
                host = '.'.join(str(b) for b in await cr.readexactly(4))
            elif atype == 0x03:
                n = (await cr.readexactly(1))[0]
                host = (await cr.readexactly(n)).decode()
            elif atype == 0x04:
                import ipaddress
                host = str(ipaddress.IPv6Address(await cr.readexactly(16)))
            else:
                return
            port = struct.unpack('!H', await cr.readexactly(2))[0]
            logger.info(f"[{self.name}] SOCKS5 {peer} → {host}:{port}")

            ur, uw = await open_outbound_connection(host, port, self.upstream)
            cw.write(b'\x05\x00\x00\x01' + b'\x00'*6)
            await cw.drain()
            await asyncio.gather(pipe(cr, uw), pipe(ur, cw))

        except Exception as e:
            logger.warning(f"[{self.name}] SOCKS5 error {peer}: {e}")
            try:
                cw.write(b'\x05\x01\x00\x01' + b'\x00'*6)
            except Exception:
                pass
        finally:
            try:
                cw.close()
            except Exception:
                pass


# ── Main Multi-Channel Daemon ────────────────────────────────────────────────

async def main():
    personas = load_personas()

    husband_cfg = personas.get("husband", DEFAULT_PERSONAS["husband"])
    wife_cfg = personas.get("wife", DEFAULT_PERSONAS["wife"])

    http_port_a = int(husband_cfg.get("http_port", 8888))
    socks_port_a = int(husband_cfg.get("socks_port", 1080))
    upstream_a = husband_cfg.get("upstream", "direct")

    http_port_b = int(wife_cfg.get("http_port", 8889))
    socks_port_b = int(wife_cfg.get("socks_port", 1081))
    upstream_b = wife_cfg.get("upstream", f"socks5://{wife_cfg.get('exit_node', '100.87.198.99')}:9888")

    berveno_cfg = personas.get("berveno", DEFAULT_PERSONAS["berveno"])
    http_port_c = int(berveno_cfg.get("http_port", 8890))
    socks_port_c = int(berveno_cfg.get("socks_port", 1082))
    upstream_c = berveno_cfg.get("upstream", "direct")

    def get_husband_headers():
        p = load_personas().get("husband", DEFAULT_PERSONAS["husband"])
        return {
            'Accept-Language': p.get("lang", "de-CH,de;q=0.9,en;q=0.8"),
            'User-Agent': p.get("user_agent", DEFAULT_PERSONAS["husband"]["user_agent"]),
            'Sec-CH-UA': p.get("sec_ch_ua", DEFAULT_PERSONAS["husband"]["sec_ch_ua"]),
            'Sec-CH-UA-Mobile': '?0',
            'Sec-CH-UA-Platform': '"Windows"',
        }

    def get_wife_headers():
        p = load_personas().get("wife", DEFAULT_PERSONAS["wife"])
        return {
            'Accept-Language': p.get("lang", "de-CH,de;q=0.9,fr-CH;q=0.8,en;q=0.7"),
            'User-Agent': p.get("user_agent", DEFAULT_PERSONAS["wife"]["user_agent"]),
            'Sec-CH-UA': p.get("sec_ch_ua", DEFAULT_PERSONAS["wife"]["sec_ch_ua"]),
            'Sec-CH-UA-Mobile': '?0',
            'Sec-CH-UA-Platform': '"Windows"',
        }

    def get_berveno_headers():
        p = load_personas().get("berveno", DEFAULT_PERSONAS["berveno"])
        return {
            'Accept-Language': p.get("lang", "de-CH,de;q=0.9,en-US;q=0.8,en;q=0.7"),
            'User-Agent': p.get("user_agent", DEFAULT_PERSONAS["berveno"]["user_agent"]),
            'Sec-CH-UA': p.get("sec_ch_ua", DEFAULT_PERSONAS["berveno"]["sec_ch_ua"]),
            'Sec-CH-UA-Mobile': '?0',
            'Sec-CH-UA-Platform': '"Windows"',
        }

    channel_a_http = HttpProxyChannel("PersonaA_Husband", upstream_a, get_husband_headers)
    channel_a_socks = Socks5ProxyChannel("PersonaA_Husband", upstream_a)

    channel_b_http = HttpProxyChannel("PersonaB_Wife", upstream_b, get_wife_headers)
    channel_b_socks = Socks5ProxyChannel("PersonaB_Wife", upstream_b)

    channel_c_http = HttpProxyChannel("PersonaC_Berveno", upstream_c, get_berveno_headers)
    channel_c_socks = Socks5ProxyChannel("PersonaC_Berveno", upstream_c)

    srv_a_http = await asyncio.start_server(channel_a_http.handle_client, BIND, http_port_a)
    srv_a_socks = await asyncio.start_server(channel_a_socks.handle_client, BIND, socks_port_a)

    srv_b_http = await asyncio.start_server(channel_b_http.handle_client, BIND, http_port_b)
    srv_b_socks = await asyncio.start_server(channel_b_socks.handle_client, BIND, socks_port_b)

    srv_c_http = await asyncio.start_server(channel_c_http.handle_client, BIND, http_port_c)
    srv_c_socks = await asyncio.start_server(channel_c_socks.handle_client, BIND, socks_port_c)

    logger.info("=== Multi-Persona Swiss Proxy Engine (Husband / Wife / Berveno) Started ===")
    logger.info(f"Channel A ({husband_cfg.get('name')}): HTTP {BIND}:{http_port_a} | SOCKS5 {BIND}:{socks_port_a} | Upstream: {upstream_a}")
    logger.info(f"Channel B ({wife_cfg.get('name')}): HTTP {BIND}:{http_port_b} | SOCKS5 {BIND}:{socks_port_b} | Upstream: {upstream_b}")
    logger.info(f"Channel C ({berveno_cfg.get('name')}): HTTP {BIND}:{http_port_c} | SOCKS5 {BIND}:{socks_port_c} | Upstream: {upstream_c}")

    async with srv_a_http, srv_a_socks, srv_b_http, srv_b_socks, srv_c_http, srv_c_socks:
        await asyncio.gather(
            srv_a_http.serve_forever(),
            srv_a_socks.serve_forever(),
            srv_b_http.serve_forever(),
            srv_b_socks.serve_forever(),
            srv_c_http.serve_forever(),
            srv_c_socks.serve_forever(),
        )


if __name__ == '__main__':
    asyncio.run(main())
