function FindProxyForURL(url, host) {
    // Convert host to lowercase for consistent matching
    var lhost = host.toLowerCase();

    // 1. Direct local & private network traffic (bypasses proxy)
    if (isPlainHostName(host) ||
        shExpMatch(lhost, "*.local") ||
        isInNet(host, "127.0.0.0", "255.0.0.0") ||
        isInNet(host, "10.0.0.0", "255.0.0.0") ||
        isInNet(host, "172.16.0.0", "255.240.0.0") ||
        isInNet(host, "192.168.0.0", "255.255.0.0") ||
        isInNet(host, "100.64.0.0", "255.192.0.0")) {
        return "DIRECT";
    }

    // 2. ALL Web Traffic in this browser session -> Route via Swiss Oracle Proxy
    // Primary HTTP Proxy with header injection on :8888, Fallback SOCKS5 on :1080
    return "PROXY 100.66.97.93:8888; SOCKS5 100.66.97.93:1080";
}
