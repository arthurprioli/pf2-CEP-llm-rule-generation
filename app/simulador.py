import requests
import time
import random

SIDDHI_ENDPOINT = "http://localhost:8080/eventos"

eventos = [
    {"usuario": "joao_silva", "texto": "Vi jogo do Fluminense ontem", "dispositivo": "PC"},
    {"usuario": "maria_souza", "texto": "Convocação da seleção brasileira", "dispositivo": "iPhone"},
    {"usuario": "elon_musk_fa", "texto": "Guerra no Irã", "dispositivo": "Android"},
    {"usuario": "marcos_villas", "texto": "Lutei com um canguru", "dispositivo": "PC"},
    {"usuario": "donald_trump_10", "texto": "Bombas jogadas no Irã", "dispositivo": "iPhone"},
    {"usuario": "luca_ribeiro", "texto": "Album novo da chappelle roan", "dispositivo": "PC"},
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