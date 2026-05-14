def get_error_html(error_message, start_latlng=None, end_latlng=None):
    """Generate a compact, user-friendly HTML error page for mobile screens."""
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
        <title>Oops! - Rainy Road</title>
        <style>
            html {{
                /* Evita qualquer rolagem indesejada */
                overflow: hidden;
            }}
            body {{
                margin: 0; 
                padding: 16px;
                box-sizing: border-box;
                background: transparent; 
                
                /* MUDANÇA AQUI: Usa apenas aprox 2/3 da tela e alinha ao topo */
                height: 66vh; 
                
                display: flex; 
                justify-content: center; 
                align-items: flex-start; /* Alinha ao topo em vez de centralizar */
                padding-top: 5vh; /* Dá um leve respiro no topo */
                font-family: system-ui, -apple-system, sans-serif;
            }}
            .card {{
                background: rgba(255, 255, 255, 0.75); 
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.4);
                border-radius: 24px; 
                width: 100%; 
                max-width: 340px;
                padding: 32px 24px; 
                text-align: center; 
                box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
                color: #1c1b1f;
            }}
            .icon {{ font-size: 40px; margin-bottom: 12px; }}
            h1 {{ font-size: 20px; margin: 0 0 16px; font-weight: 600; }}
            .error-row {{
                display: flex; gap: 8px; align-items: stretch; margin-bottom: 20px;
            }}
            .error-box {{
                background: rgba(255, 255, 255, 0.6); 
                color: #b3261e; 
                padding: 12px; 
                border-radius: 12px;
                font-family: ui-monospace, SFMono-Regular, monospace; 
                font-size: 13px; 
                white-space: nowrap; 
                overflow-x: auto; 
                border: 1px solid rgba(179, 38, 30, 0.2); 
                flex: 1; 
                text-align: left; 
                margin: 0;
            }}
            .copy-btn {{
                background: rgba(255, 255, 255, 0.8); 
                color: #4b5563; 
                border: 1px solid rgba(0, 0, 0, 0.05);
                border-radius: 12px; 
                padding: 0 12px; 
                cursor: pointer; 
                font-size: 18px;
                transition: all 0.2s ease; 
                display: flex; 
                align-items: center; 
                justify-content: center;
            }}
            .copy-btn:hover {{ background: #fff; }}
            .copy-btn:active {{ transform: scale(0.95); }}
            .hints {{
                font-size: 14px; 
                color: #49454f; 
                text-align: left; 
                margin: 0;
            }}
            .hints p {{ margin: 0 0 8px; font-weight: 600; color: #1c1b1f; }}
            .hints ul {{ margin: 0; padding-left: 20px; line-height: 1.6; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">🌧️</div>
            <h1>Não foi possível gerar o mapa</h1>
            <div class="error-row">
                <div class="error-box" id="errMsg">{error_message}</div>
                <button class="copy-btn" onclick="navigator.clipboard.writeText(document.getElementById('errMsg').innerText).then(() => this.innerText='✓')" title="Copiar erro">📋</button>
            </div>
            <div class="hints">
                <p>💡 Como resolver:</p>
                <ul>
                    <li>Tente rotas mais curtas</li>
                    <li>Verifique se a rota selecionada é acessível para o modo selecionado</li>
                    <li>Você pode tentar usar outras cidades próximas</li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """