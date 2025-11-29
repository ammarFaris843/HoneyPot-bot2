from flask import Flask, jsonify
from threading import Thread
import time
import os
from datetime import datetime, timezone

app = Flask('')

# Supabase credentials
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>GOONER MACHINE BOT</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: 'Courier New', monospace;
                background: #0a0a0a;
                color: #ccc;
                min-height: 100vh;
                padding: 40px 20px;
            }}
            .container {{
                max-width: 900px;
                margin: 0 auto;
            }}
            header {{
                margin-bottom: 50px;
            }}
            h1 {{
                font-size: 2em;
                margin-bottom: 15px;
                font-weight: normal;
                letter-spacing: 2px;
            }}
            .status-badge {{
                display: inline-block;
                color: #1db854;
                padding: 6px 12px;
                font-weight: normal;
                margin-top: 15px;
                border: 1px solid #1db854;
                background: transparent;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 30px;
                margin-bottom: 50px;
            }}
            .card {{
                background: #111;
                padding: 30px;
                border: 1px solid #222;
            }}
            .card:hover {{
                border-color: #333;
            }}
            .stat-number {{
                font-size: 2em;
                font-weight: normal;
                margin: 15px 0;
                color: #1db854;
                font-family: 'Courier New', monospace;
            }}
            .stat-label {{
                font-size: 0.85em;
                opacity: 0.6;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            .section {{
                background: #111;
                padding: 30px;
                margin-bottom: 50px;
                border: 1px solid #222;
            }}
            .section h2 {{
                margin-bottom: 25px;
                font-size: 1.2em;
                border-bottom: 1px solid #333;
                padding-bottom: 15px;
                font-weight: normal;
            }}
            .info {{
                background: transparent;
                padding: 12px 0;
                margin: 15px 0;
                border-left: 2px solid #333;
                padding-left: 15px;
                line-height: 1.6;
            }}
            .footer {{
                text-align: center;
                margin-top: 60px;
                opacity: 0.5;
                font-size: 0.85em;
                border-top: 1px solid #222;
                padding-top: 30px;
            }}
            .refresh-timer {{
                text-align: center;
                margin-top: 20px;
                opacity: 0.4;
                font-size: 0.8em;
            }}
            .database-status {{
                padding: 12px 0;
                margin-top: 20px;
                border-left: 2px solid #333;
                padding-left: 15px;
            }}
            code {{
                background: transparent;
                padding: 0;
                color: #1db854;
                font-family: 'Courier New', monospace;
            }}
            @media (max-width: 768px) {{
                h1 {{
                    font-size: 1.5em;
                }}
                .grid {{
                    grid-template-columns: 1fr;
                    gap: 20px;
                }}
                body {{
                    padding: 20px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>GOONER MACHINE BOT DASHBOARD</h1>
                <div class="status-badge">ONLINE</div>
            </header>
            
            <div class="grid">
                <div class="card">
                    <div class="stat-label">Status</div>
                    <div class="stat-number">ACTIVE</div>
                </div>
                <div class="card">
                    <div class="stat-label">Service</div>
                    <div style="margin-top: 15px; font-size: 1.1em;">Honeypot Protection</div>
                </div>
                <div class="card">
                    <div class="stat-label">Current Time</div>
                    <div style="margin-top: 15px; font-size: 0.95em;" id="current-time">
                        {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>Bot Information</h2>
                <div class="info">
                    <strong>Service:</strong> GOONER MACHINE BOT
                </div>
                <div class="info">
                    <strong>Status:</strong> Running & Monitoring
                </div>
                <div class="info">
                    <strong>Slash Commands:</strong> 7 Available
                </div>
                <div class="database-status">
                    <strong>Database:</strong> Connected to Supabase
                </div>
            </div>
            
            <div class="section">
                <h2>API Endpoints</h2>
                <div class="info">
                    <code>/health</code> - Health check<br>
                    <code>/status</code> - Service status<br>
                    <code>/api/stats</code> - Real-time statistics
                </div>
            </div>
            
            <div class="section">
                <h2>Available Slash Commands</h2>
                <div class="info">
                    <code>/createhoneypot</code> - Create honeypot channel<br>
                    <code>/createlog</code> - Create log channel<br>
                    <code>/sethoneypot</code> - Set honeypot channel<br>
                    <code>/setlog</code> - Set log channel<br>
                    <code>/honeypotconfig</code> - View configuration<br>
                    <code>/honeypotstats</code> - View statistics<br>
                    <code>/banhistory</code> - View ban history
                </div>
            </div>
            
            <div class="footer">
                <p>Discord Honeypot Protection System • Built with Discord.py</p>
                <div class="refresh-timer">Dashboard updates every <strong>30 seconds</strong></div>
            </div>
        </div>
        
        <script>
            function updateTime() {{
                const now = new Date();
                const utc = now.toLocaleTimeString('en-US', {{ timeZone: 'UTC' }}) + ' UTC';
                document.getElementById('current-time').textContent = utc;
            }}
            updateTime();
            setInterval(updateTime, 1000);
            
            // Auto-refresh page every 30 seconds
            setTimeout(function() {{
                location.reload();
            }}, 30000);
        </script>
    </body>
    </html>
    """

@app.route('/health')
def health():
    """Health check endpoint - keeps bot alive"""
    return jsonify({
        "status": "healthy",
        "service": "honeypot-bot",
        "timestamp": time.time(),
        "uptime": "running"
    })

@app.route('/status')
def status():
    """Status endpoint"""
    return jsonify({
        "bot": "online",
        "service": "honeypot-protection",
        "dashboard": "active",
        "database": "connected"
    })

@app.route('/api/stats')
def api_stats():
    """API endpoint for stats"""
    return jsonify({
        "status": "active",
        "bot_name": "HATSUNE MIKU HATE CLANKER",
        "service": "honeypot-protection",
        "timestamp": time.time()
    })

def run():
    app.run(host='0.0.0.0', port=5001, debug=False)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()
