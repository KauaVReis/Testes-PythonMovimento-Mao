import cv2
import mediapipe as mp
import math
import time
import os

# --- Configurações Iniciais ---
mp_hands = mp.solutions.hands
# Vamos procurar apenas 1 mão para este teste
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

# Captura de vídeo
cap = cv2.VideoCapture(0)
WIDTH, HEIGHT = 1280, 720
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)

# Criar a pasta "fotos" se ela não existir
output_folder = "fotos"
os.makedirs(output_folder, exist_ok=True)

# --- Função de Detecção de Dedos (do nosso outro app) ---
def detectar_dedos_vetorial(lm_list):
    """
    Detecta quais dedos estão estendidos usando ângulos vetoriais.
    Retorna uma lista de 5 elementos (0 ou 1) para [polegar, indicador, medio, anelar, minimo].
    """
    dedos = []
    def dedo_estendido(p1, p2, p3):
        # Calcula vetores
        v1 = (p2[0] - p1[0], p2[1] - p1[1])
        v2 = (p3[0] - p2[0], p3[1] - p2[1])
        # Produto escalar
        dot = v1[0]*v2[0] + v1[1]*v2[1]
        # Normas
        norm1 = math.hypot(v1[0], v1[1])
        norm2 = math.hypot(v2[0], v2[1])
        # Ângulo
        cos_angle = dot / (norm1 * norm2 + 1e-6) # 1e-6 para evitar divisão por zero
        angle = math.acos(min(1, max(-1, cos_angle))) # Garante que o valor esteja em [-1, 1]
        # Se o ângulo for pequeno (quase reto), o dedo está estendido
        return angle < math.radians(30) # Limite de 30 graus
    
    try:
        # Polegar: usa landmarks 2 (base), 3 (meio), 4 (ponta)
        dedos.append(int(dedo_estendido(lm_list[2], lm_list[3], lm_list[4])))
        # Indicador: usa landmarks 5 (base), 6 (meio), 8 (ponta)
        dedos.append(int(dedo_estendido(lm_list[5], lm_list[6], lm_list[8])))
        # Médio: usa landmarks 9 (base), 10 (meio), 12 (ponta)
        dedos.append(int(dedo_estendido(lm_list[9], lm_list[10], lm_list[12])))
        # Anelar: usa landmarks 13 (base), 14 (meio), 16 (ponta)
        dedos.append(int(dedo_estendido(lm_list[13], lm_list[14], lm_list[16])))
        # Mínimo: usa landmarks 17 (base), 18 (meio), 20 (ponta)
        dedos.append(int(dedo_estendido(lm_list[17], lm_list[18], lm_list[20])))
    except:
        return [0,0,0,0,0] # Retorna punho fechado em caso de erro
    
    return dedos

# --- Variáveis de Estado para o Timer ---
app_state = "IDLE" # Pode ser "IDLE", "ARMING", "POSING", "CAPTURED"
timer_start_time = 0 # Tempo em que o timer atual começou
flash_start_time = 0 # Tempo em que o flash começou
TIMER_ARMING = 2 # 2 segundos para armar
TIMER_POSING = 5 # 5 segundos para a pose

print("Iniciando... Pressione 'q' ou ESC para sair...")

# --- Loop Principal ---
while True:
    # --- 'img_raw' é a imagem limpa, original da câmera ---
    success, img_raw = cap.read()
    if not success:
        print("Erro ao ler a câmera.")
        break

    # 'img' (para display) é um flip (espelho) da 'img_raw'
    # É nesta 'img' que vamos desenhar os textos e landmarks
    img = cv2.flip(img_raw, 1)
    
    # Processamento do MediaPipe
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)
    
    overlay_text = ""
    countdown_text = ""
    is_hand_open = False # Reseta a detecção de mão aberta a cada frame
    
    # Se uma mão for detectada
    if results.multi_hand_landmarks:
        # Pegar a primeira mão detectada
        handLms = results.multi_hand_landmarks[0]
        
        lm_list = []
        for lm in handLms.landmark:
            lm_list.append((int(lm.x * WIDTH), int(lm.y * HEIGHT)))

        # Detectar os dedos
        dedos = detectar_dedos_vetorial(lm_list)
        
        # Gesto de mão aberta
        is_hand_open = (dedos == [1, 1, 1, 1, 1])
        
        # Desenhar os landmarks (APENAS na imagem de display 'img')
        mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS)

    # --- Lógica de Estados da Câmera (AGORA FORA DO IF DA MÃO) ---
    
    # ESTADO 1: Ocioso, esperando a mão abrir
    if app_state == "IDLE":
        overlay_text = "Mostre a mao aberta para comecar"
        if is_hand_open: # Só acontece se a mão foi detectada (is_hand_open == True)
            app_state = "ARMING" # Inicia o primeiro timer
            timer_start_time = time.time()
            print("Mão aberta detectada! Armando em 2s...")

    # ESTADO 2: Mão detectada, contando 2s para "Armar"
    # Este bloco agora roda mesmo se a mão desaparecer
    elif app_state == "ARMING": 
        time_elapsed = time.time() - timer_start_time
        countdown_value = TIMER_ARMING - int(time_elapsed)
        
        if countdown_value > 0:
            countdown_text = str(countdown_value)
            overlay_text = "Prepare-se..."
        else:
            # Transição para o próximo estado
            app_state = "POSING"
            timer_start_time = time.time() # Reseta o timer
            print("Armado! Faca a pose...")
    
    # ESTADO 3: Contando 5s para a "Pose"
    # Este bloco agora roda mesmo se a mão desaparecer
    elif app_state == "POSING": 
        time_elapsed = time.time() - timer_start_time
        countdown_value = TIMER_POSING - int(time_elapsed)
        
        if countdown_value > 0:
            countdown_text = str(countdown_value)
            overlay_text = "Faca a pose!"
        else:
            # Tirar a foto
            filename = os.path.join(output_folder, f"foto_{int(time.time())}.jpg")
            
            # Salva a imagem LIMPA (img_raw), mas flipada para corresponder ao display
            img_clean_flipped = cv2.flip(img_raw, 1)
            cv2.imwrite(filename, img_clean_flipped) 
            print(f"Foto salva: {filename}")
            
            app_state = "CAPTURED"
            flash_start_time = time.time()
    
    # (O BLOCO 'ELSE' QUE RESETAVA FOI REMOVIDO)
        
    # ESTADO 4: A foto foi tirada, mostrar feedback
    if app_state == "CAPTURED":
        overlay_text = "FOTO CAPTURADA!"
        
        # Efeito de "flash" (tela branca por 0.5 seg)
        if time.time() - flash_start_time < 0.5:
            cv2.rectangle(img, (0, 0), (WIDTH, HEIGHT), (255, 255, 255), -1)
        else:
            app_state = "IDLE" # Volta ao estado inicial

    # --- Desenhar a Interface (Textos e Contadores) ---
    
    # Texto de instrução (Ex: "Faca a pose!")
    if overlay_text:
        cv2.putText(img, overlay_text, (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 6) # Sombra
        cv2.putText(img, overlay_text, (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2) # Texto
        
    # Texto da contagem (Ex: "5")
    if countdown_text:
        # Posição do contador (canto superior direito)
        font_scale = 5.0
        thickness = 15
        text_size = cv2.getTextSize(countdown_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]
        
        # Posição X = Largura total - largura do texto - margem
        text_x = WIDTH - text_size[0] - 50 
        # Posição Y = Altura do texto + margem
        text_y = text_size[1] + 50         
        
        # Desenha a sombra do número
        cv2.putText(img, countdown_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), thickness + 10)
        # Desenha o número
        cv2.putText(img, countdown_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 255), thickness)


    # Mostrar Imagem Final
    cv2.imshow("Teste de Camera por Gesto", img)

    key = cv2.waitKey(1)
    if key == 27 or key == ord('q'): # Pressione ESC ou 'q' para sair
        break

# Limpeza
cap.release()
cv2.destroyAllWindows()