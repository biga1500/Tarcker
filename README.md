# Tarcker 📊

Monitor de atividades para Linux/macOS/Windows que rastreia o que você faz no computador e envia um resumo diário com gráficos.

## Funcionalidades

- **Rastreamento de janela ativa** — registra qual app está em foco e por quanto tempo
- **Detecção de ociosidade** — pausa o rastreamento quando você está inativo
- **Categorização automática** — classifica apps em: código, browser, comunicação, produtividade, entretenimento, design
- **Resumo diário em texto** — exibido no terminal com gráfico de barras
- **Relatório HTML** — salvo em `~/.tarcker/reports/` com visual moderno
- **Notificação desktop** — popup ao final do dia
- **Envio por e-mail** — resumo enviado via SMTP (opcional)
- **Agendamento automático** — dispara o resumo no horário configurado (padrão: 18h)

## Instalação

### Linux (Debian/Ubuntu)

```bash
# Instale as dependências do sistema
sudo apt install xdotool xprintidle libnotify-bin

# Configure e instale o serviço systemd
bash setup.sh
```

### Executar manualmente

```bash
python3 main.py
```

## Uso

```bash
# Iniciar o daemon (rastrear + agendar resumo)
python3 main.py

# Gerar resumo de hoje agora
python3 main.py --summary

# Resumo de ontem
python3 main.py --summary yesterday

# Resumo de uma data específica
python3 main.py --summary 2026-03-15

# Ver onde fica o arquivo de configuração
python3 main.py --config

# Logs detalhados
python3 main.py --verbose
```

## Configuração

O arquivo de configuração fica em `~/.tarcker/config.json` e é criado automaticamente na primeira execução.

### Opções principais

```jsonc
{
  "poll_interval": 5,          // Frequência de verificação (segundos)
  "idle_threshold": 120,       // Tempo ocioso para pausar rastreamento (segundos)
  "summary_time": "18:00",     // Horário do resumo diário

  "email": {
    "enabled": false,          // true para ativar envio por e-mail
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "use_tls": true,
    "username": "seu@email.com",
    "password": "sua_senha_de_app",
    "from_addr": "seu@email.com",
    "to_addr": "destino@email.com"
  },

  "desktop_notification": {
    "enabled": true             // Notificação popup ao final do dia
  },

  "html_report": {
    "enabled": true,
    "output_dir": "~/.tarcker/reports"  // Onde salvar os relatórios HTML
  }
}
```

> **Gmail**: Use uma [Senha de App](https://myaccount.google.com/apppasswords) em vez da senha normal.

### Categorias personalizadas

Adicione palavras-chave para categorizar seus apps:

```json
"categories": {
  "code": ["vscode", "terminal", "vim"],
  "browser": ["firefox", "chrome"],
  "minha_categoria": ["meu_app"]
}
```

## Serviço systemd (Linux)

```bash
# Habilitar na inicialização do sistema
systemctl --user daemon-reload
systemctl --user enable --now tarcker

# Ver logs em tempo real
journalctl --user -u tarcker -f
```

## Estrutura do projeto

```
Tarcker/
├── main.py               # Ponto de entrada / CLI
├── setup.sh              # Script de instalação (Linux)
├── requirements.txt      # Dependências
└── tarcker/
    ├── config.py         # Configurações
    ├── database.py       # Armazenamento SQLite
    ├── tracker.py        # Rastreamento de janelas e ociosidade
    ├── summarizer.py     # Geração de resumos (texto + HTML)
    ├── notifier.py       # Notificações (desktop + e-mail)
    └── scheduler.py      # Agendador do resumo diário
```

## Dados armazenados

Tudo fica em `~/.tarcker/`:
- `config.json` — configurações
- `activity.db` — banco de dados SQLite com sessões e períodos ociosos
- `reports/` — relatórios HTML diários
