#!/usr/bin/env python3
"""
smart_proxy.py — Swiss geo-masking proxy
  HTTP  proxy : 0.0.0.0:8888  (handles CONNECT for HTTPS + plain HTTP)
  SOCKS5 proxy: 0.0.0.0:1080  (chains to upstream)

All traffic is forwarded through tablet SOCKS5 → Swiss VPN → Zürich exit IP.
Swiss headers injected on every plain-HTTP request.
"""

import asyncio
import struct
import logging
import re

import aiohttp
from aiohttp_socks import ProxyConnector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

UPSTREAM      = ('100.100.74.9', 9888)   # tablet SOCKS5 → Swiss VPN
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
}
STRIP_REQ = {
    'x-forwarded-for', 'x-real-ip', 'via', 'forwarded',
    'proxy-connection', 'proxy-authorization',
}


# ── Upstream SOCKS5 connect ───────────────────────────────────────────────────

async def upstream_connect(host: str, port: int):
    """Open a tunnel through the tablet SOCKS5 to (host, port)."""
    r, w = await asyncio.open_connection(*UPSTREAM)
    # Handshake
    w.write(b'\x05\x01\x00')
    await w.drain()
    if (await r.readexactly(2))[1] != 0x00:
        raise ConnectionError('upstream auth failed')
    # CONNECT
    hb = host.encode()
    w.write(b'\x05\x01\x00\x03' + bytes([len(hb)]) + hb + struct.pack('!H', port))
    await w.drain()
    rep = await r.readexactly(4)
    if rep[1] != 0x00:
        raise ConnectionError(f'upstream connect error {rep[1]}')
    atype = rep[3]
    if   atype == 1: await r.readexactly(4)
    elif atype == 3: await r.readexactly((await r.readexactly(1))[0])
    elif atype == 4: await r.readexactly(16)
    await r.readexactly(2)
    return r, w


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
                ur, uw = await upstream_connect(host, port)
            except Exception as e:
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

        # Build clean headers for upstream
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

        # Forward via aiohttp through upstream SOCKS5
        try:
            connector = ProxyConnector.from_url(
                f'socks5://{UPSTREAM[0]}:{UPSTREAM[1]}', ssl=False
            )
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


# ── SOCKS5 proxy (chains to upstream) ────────────────────────────────────────

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

        ur, uw = await upstream_connect(host, port)
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
    logger.info(f"Upstream    : socks5://{UPSTREAM[0]}:{UPSTREAM[1]}  (Swiss VPN)")
    async with h_srv, s_srv:
        await asyncio.gather(
            h_srv.serve_forever(),
            s_srv.serve_forever(),
        )

if __name__ == '__main__':
    asyncio.run(main())
