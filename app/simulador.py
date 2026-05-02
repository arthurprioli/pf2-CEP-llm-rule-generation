import requests
import time
import random

SIDDHI_ENDPOINT = "http://localhost:8080/eventos"

eventos = [
    {"usuario": "joao_silva", "texto": "Login realizado com sucesso", "acao": "login"},
    {"usuario": "maria_souza", "texto": "Adicionou sapato ao carrinho", "acao": "navegacao"},
    {"usuario": "HACKER_99", "texto": "Tentativa de injeção SQL falhou", "acao": "ataque_db"},
    {"usuario": "bot_russo", "texto": "1000 tentativas de login falhadas", "acao": "brute_force"},
    {"usuario": "pedro_alves", "texto": "Compra de R$ 50,00 aprovada", "acao": "compra_normal"},
    {"usuario": "conta_falsa", "texto": "Compra de R$ 15.000,00 às 3h da manhã", "acao": "compra_suspeita"}
]

print(f"🚀 Iniciando canhão de dados para: {SIDDHI_ENDPOINT}\n")

for i in range(15):
    evento_sorteado = random.choice(eventos)
    
    # Envelope de evento
    payload_formatado = {"event": evento_sorteado}
    
    try:
        # Repare que removemos o auth=('admin', 'admin') aqui!
        resposta = requests.post(
            SIDDHI_ENDPOINT, 
            json=payload_formatado,
            timeout=5
        )
        
        if resposta.status_code in [200, 201, 202]:
            print(f"[SUCESSO] Enviado: {evento_sorteado['texto']}")
        else:
            print(f"[ERRO {resposta.status_code}] Falha: {resposta.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"[ERRO DE REDE] Falha: {e}")
    
    time.sleep(0.5)

print("\n✅ Fluxo finalizado! Cache alimentado.")