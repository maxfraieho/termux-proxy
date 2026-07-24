#!/usr/bin/env python3
"""
smart_proxy.py — Swiss geo-masking proxy
  HTTP  proxy : 0.0.0.0:8888  (handles CONNECT for HTTPS + plain HTTP with Swiss headers)
  SOCKS5 proxy: 0.0.0.0:1080  (handles TCP tunnel connections)

All outgoing OS traffic from this process (user: swissproxy) is routed by Linux
Kernel Policy Routing (table 200 via iptables -m owner) through the Tailscale Exit Node (100.100.74.9).
"""

import asyncio
import struct
import logging

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

HTTP_PORT     = 8888
SOCKS5_PORT   = 1080
BIND          = '0.0.0.0'
BUF           = 65536

SWISS_HEADERS = {
    'Accept-Language': 'de-CH,de;q=0.9,fr-CH;q=0.8,en;q=0.7',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Sec-CH-UA': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'Sec-CH-UA-Mobile': '?0',
    'Sec-CH-UA-Platform': '"Windows"',
}
STRIP_REQ = {
    'x-forwarded-for', 'x-real-ip', 'via', 'forwarded',
    'proxy-connection', 'proxy-authorization', 'cf-connecting-ip',
    'true-client-ip', 'x-client-ip', 'client-ip', 'x-cluster-client-ip'
}


# ── Direct OS connect (routed via kernel policy routing to Exit Node) ────────

async def direct_connect(host: str, port: int):
    """Open a direct OS TCP socket to (host, port).
    Kernel Policy Routing (table 200) automatically routes this socket through
    the Tailscale Exit Node (100.100.74.9).
    """
    return await asyncio.open_connection(host, port)


# ── Pipe ─────────────────────────────────────────────────────────────────────

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
        try: dst.close()
        except Exception: pass


# ── HTTP proxy (raw TCP) ──────────────────────────────────────────────────────

async def http_proxy_client(cr, cw):
    """Handle one HTTP proxy client connection."""
    peer = cw.get_extra_info('peername', ('?', 0))[0]
    try:
        # Read request line + headers (up to 16 KB)
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
        method, path, _ = req_line.split(' ', 2)

        # ── CONNECT (HTTPS tunnel) ──────────────────────────────────────────
        if method == 'CONNECT':
            host, _, port = path.rpartition(':')
            port = int(port or 443)
            logger.info(f"CONNECT {host}:{port} from {peer}")
            try:
                ur, uw = await direct_connect(host, port)
            except Exception as e:
                logger.warning(f"CONNECT error {host}:{port} — {e}")
                cw.write(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
                await cw.drain()
                return
            cw.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
            await cw.drain()
            await asyncio.gather(pipe(cr, uw), pipe(ur, cw))
            return

        # ── Plain HTTP ──────────────────────────────────────────────────────
        # Parse headers
        req_headers = {}
        for ln in lines[1:]:
            if ':' in ln:
                k, _, v = ln.partition(':')
                req_headers[k.strip().lower()] = v.strip()

        host = req_headers.get('host', '')
        logger.info(f"{method} {path[:70]} from {peer}")

        # Build clean headers with Swiss fingerprint injection
        fwd_headers = {
            k: v for k, v in req_headers.items()
            if k not in STRIP_REQ
        }
        fwd_headers.update({k.lower(): v for k, v in SWISS_HEADERS.items()})

        # Read remaining body if Content-Length present
        body = body_start
        clen = int(req_headers.get('content-length', 0))
        while len(body) < clen:
            body += await cr.read(clen - len(body))

        # Forward via direct OS socket (kernel policy routes via exit node)
        try:
            async with aiohttp.ClientSession() as session:
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
                    cw.write(
                        status_line.encode() +
                        resp_hdrs.encode() +
                        b'\r\n' + rb
                    )
                    await cw.drain()
        except Exception as e:
            logger.warning(f"HTTP error: {e}")
            cw.write(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
            await cw.drain()

    except Exception as e:
        logger.debug(f"http_proxy_client error: {e}")
    finally:
        try: cw.close()
        except Exception: pass


# ── SOCKS5 proxy ─────────────────────────────────────────────────────────────

async def socks5_client(cr, cw):
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
        if   atype == 0x01:
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
        logger.info(f"SOCKS5 {peer} → {host}:{port}")

        ur, uw = await direct_connect(host, port)
        cw.write(b'\x05\x00\x00\x01' + b'\x00'*6)
        await cw.drain()
        await asyncio.gather(pipe(cr, uw), pipe(ur, cw))

    except Exception as e:
        logger.warning(f"SOCKS5 error {peer}: {e}")
        try: cw.write(b'\x05\x01\x00\x01' + b'\x00'*6)
        except Exception: pass
    finally:
        try: cw.close()
        except Exception: pass


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    h_srv = await asyncio.start_server(http_proxy_client,  BIND, HTTP_PORT)
    s_srv = await asyncio.start_server(socks5_client,       BIND, SOCKS5_PORT)
    logger.info(f"HTTP  proxy : {BIND}:{HTTP_PORT}")
    logger.info(f"SOCKS5 proxy: {BIND}:{SOCKS5_PORT}")
    logger.info("Routing     : Direct OS Policy Routing via Tailscale Exit Node (100.100.74.9)")
    async with h_srv, s_srv:
        await asyncio.gather(
            h_srv.serve_forever(),
            s_srv.serve_forever(),
        )

if __name__ == '__main__':
    asyncio.run(main())
