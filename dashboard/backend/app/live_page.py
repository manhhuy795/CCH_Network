LIVE_DASHBOARD_HTML = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CCH SDN Dashboard API</title>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #f7f8fa; color: #17202a; }
    main { max-width: 760px; margin: 72px auto; padding: 0 20px; }
    section { background: #fff; border: 1px solid #d8dee8; border-radius: 8px; padding: 24px; }
    h1 { margin: 0 0 8px; font-size: 24px; }
    p { line-height: 1.6; color: #4b5563; }
    a { color: #0f5cc0; font-weight: 700; text-decoration: none; }
    ul { line-height: 2; padding-left: 20px; }
    code { background: #eef2f7; padding: 2px 6px; border-radius: 4px; }
  </style>
</head>
<body>
  <main>
    <section>
      <h1>Hybrid MPLS L3VPN + SDN Edge Policy Demo</h1>
      <p>
        Đây là trang fallback tối giản của FastAPI. Giao diện chính là React Dashboard
        chạy tại <code>http://localhost:5173</code>. Topology, policy và metrics đều lấy qua API,
        không hardcode trong trang fallback này.
      </p>
      <ul>
        <li><a href="/docs">API Docs</a></li>
        <li><a href="/api/topology">Topology API</a></li>
        <li><a href="/api/live/status">Trạng thái runtime</a></li>
        <li>React Dashboard: <a href="http://localhost:5173">http://localhost:5173</a></li>
      </ul>
    </section>
  </main>
</body>
</html>
"""
