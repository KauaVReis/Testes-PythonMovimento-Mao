import cv2
import mediapipe as mp
# import gpiod (REMOVIDO - Específico do Raspberry Pi)
import math
import time
from collections import Counter # Importar o Counter para achar o mais comum

# --- Pinos GPIO REMOVIDOS ---
# Pinos GPIO para os 5 relés (polegar até mindinho)
# rele_pins = [14, 15, 18, 23, 24]
# chip = gpiod.Chip('gpiochip0')
# Configuração dos pinos GPIO
# rele_lines = []
# for pin in rele_pins:
# rele_line = chip.get_line(pin)
# rele_line.request(consumer='hand_tracking', type=gpiod.LINE_REQ_DIR_OUT)
# rele_lines.append(rele_line)
# Inicializa estados anteriores dos relés
# estado_rele_anterior = [0, 0, 0, 0, 0]
# --- Fim da seção REMOVIDA ---

# MediaPipe Hands
mp_hands = mp.solutions.hands
# --- 1. AUMENTAR A CONFIANÇA PARA REDUZIR RUÍDO ---
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

# Estilo leve para desenhar os pontos e conexões da mão
estilo_ponto = mp_draw.DrawingSpec(color=(0, 255, 0), thickness=1, circle_radius=1)
estilo_linha = mp_draw.DrawingSpec(color=(0, 0, 255), thickness=1)

# Captura de vídeo com resolução aumentada
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)
cap.set(cv2.CAP_PROP_FPS, 30)

# --- Configuração de Tela Cheia REMOVIDA ---
# (Pode causar problemas em alguns PCs)
# screen_width = 1024
# screen_height = 768
# cv2.namedWindow("Hand Tracking", cv2.WND_PROP_FULLSCREEN)
# cv2.setWindowProperty("Hand Tracking", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
# --- Fim da seção REMOVIDA ---

def distancia(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def detectar_dedos_vetorial(lm_list):
    dedos = []

    # Verifica o ângulo entre os segmentos dos dedos
    def dedo_estendido(p1, p2, p3):
        # Calcula o vetor entre as juntas
        v1 = (p2[0] - p1[0], p2[1] - p1[1])
        v2 = (p3[0] - p2[0], p3[1] - p2[1])
        # Produto escalar
        dot = v1[0]*v2[0] + v1[1]*v2[1]
        # Norma dos vetores
        norm1 = math.hypot(v1[0], v1[1])
        norm2 = math.hypot(v2[0], v2[1])
        # Ângulo entre os vetores
        cos_angle = dot / (norm1 * norm2 + 1e-6)
        angle = math.acos(min(1, max(-1, cos_angle)))
        # Se o ângulo for pequeno (reta), o dedo está estendido
        return angle < math.radians(30)  # menor que ~30 graus

    # Polegar: usa landmarks 2 (base), 3 (meio), 4 (ponta)
    dedos.append(int(dedo_estendido(lm_list[2], lm_list[3], lm_list[4])))

    # Indicador, Médio, Anelar, Mindinho
    dedos.append(int(dedo_estendido(lm_list[5], lm_list[6], lm_list[8])))  # indicador
    dedos.append(int(dedo_estendido(lm_list[9], lm_list[10], lm_list[12])))  # médio
    dedos.append(int(dedo_estendido(lm_list[13], lm_list[14], lm_list[16])))  # anelar
    dedos.append(int(dedo_estendido(lm_list[17], lm_list[18], lm_list[20])))  # mindinho

    return dedos

frame_count = 0
fps_target = 30
tempo_por_frame = 1.0 / fps_target

# --- 2. VARIÁVEIS PARA FILTRO DE "DEDOS FANTASMAS" ---
BUFFER_SIZE = 5 # Usar os últimos 5 frames para estabilizar
gesture_buffer = [] # Lista para armazenar os gestos recentes
stable_gesture_text = "" # O texto do gesto estabilizado

while True:
    start_time = time.time()

    success, img = cap.read()
    if not success:
        print("Erro ao ler a câmera.")
        break

    img = cv2.flip(img, 1)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)
    dedos = [0, 0, 0, 0, 0]
    
    # --- NOVAS VARIÁVEIS PARA GESTOS E MÃO ---
    current_gesture_text = "" # Gesto deste frame específico
    hand_label_text = "" # "Esquerda" ou "Direita"

    if results.multi_hand_landmarks and results.multi_handedness:
        handLms = results.multi_hand_landmarks[0]
        
        # --- IDEIA 4: IDENTIFICAR MÃO ESQUERDA/DIREITA ---
        hand_label = results.multi_handedness[0].classification[0].label
        hand_label_text = f"Mao: {hand_label}" # Ex: "Mao: Right" ou "Mao: Left"

        lm_list = []
        for lm in handLms.landmark:
            h, w, _ = img.shape
            lm_list.append((int(lm.x * w), int(lm.y * h)))

        dedos = detectar_dedos_vetorial(lm_list)

        # Desenhar landmarks
        mp_draw.draw_landmarks(
            img,
            handLms,
            mp_hands.HAND_CONNECTIONS,
            estilo_ponto,
            estilo_linha
        )
        
        # --- IDEIA 1: LÓGICA DE RECONHECIMENTO DE GESTOS ---
        
        # O 'dedos' é uma lista: [Polegar, Indicador, Medio, Anelar, Minimo]
        
        if dedos == [0, 0, 0, 0, 0]:
            current_gesture_text = "Punho Fechado"
        elif dedos == [0, 1, 0, 0, 0]:
            current_gesture_text = "1"
        elif dedos == [0, 1, 1, 0, 0]:
            current_gesture_text = "Paz / 2"
        elif dedos == [0, 1, 1, 1, 0]:
            current_gesture_text = "3"
        elif dedos == [0, 1, 1, 1, 1]:
            current_gesture_text = "4"
        elif dedos == [1, 1, 1, 1, 1]:
            current_gesture_text = "Mao Aberta / 5"
        elif dedos == [1, 0, 0, 0, 0]:
            current_gesture_text = "Joia"
        elif dedos == [1, 0, 0, 0, 1]:
            current_gesture_text = "Telefone"
        else:
            # Se for um gesto não reconhecido, mostramos a contagem
            count = dedos.count(1)
            current_gesture_text = f"Dedos: {count}"

        # --- REMOVIDO (Contador antigo) ---
        # current_total_fingers = dedos.count(1)


        # --- REMOVIDO (Mostrava a contagem instantânea) ---
        # 2. Escrever o número total na tela
        # (Coloca um fundo preto para legibilidade)
        # cv2.putText(img, str(total_fingers), (30, 75), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 10)
        # (Coloca o texto branco por cima)
        # cv2.putText(img, str(total_fingers), (30, 75), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 5)
        # --- FIM DA SEÇÃO REMOVIDA ---


        # --- REMOVIDO (Mostrava a numeração individual) ---
        # Mostrar a numeração dos dedos apenas se estiverem levantados
        # dedo_nomes = ['1', '2', '3', '4', '5']
        # pontas_dedos = [4, 8, 12, 16, 20]
        #
        # for i, idx in enumerate(pontas_dedos):
        #     if dedos[i]:  
        #         x, y = lm_list[idx]
        #         cv2.putText(img, dedo_nomes[i], (x - 10, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
        #         cv2.putText(img, dedo_nomes[i], (x - 10, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        # --- FIM DA SEÇÃO REMOVIDA ---

    # --- 3. LÓGICA DO FILTRO DE ESTABILIZAÇÃO (Agora com texto) ---
    
    # Adiciona o gesto atual ao buffer
    gesture_buffer.append(current_gesture_text)
    
    # Mantém o buffer com o tamanho máximo (BUFFER_SIZE)
    if len(gesture_buffer) > BUFFER_SIZE:
        gesture_buffer.pop(0) # Remove o gesto mais antigo

    # Só atualiza a contagem estável se o buffer estiver cheio
    if len(gesture_buffer) == BUFFER_SIZE:
        # Conta a ocorrência de cada gesto no buffer
        # Ex: ['Paz / 2', 'Paz / 2', '1'] -> Counter({'Paz / 2': 2, '1': 1})
        count_data = Counter(gesture_buffer)
        
        # Pega o gesto mais comum
        most_common_gesture = count_data.most_common(1)[0][0]
        
        # Pega a frequência desse gesto
        most_common_freq = count_data.most_common(1)[0][1]
        
        # Só atualiza se o gesto mais comum aparecer em mais da metade
        if most_common_freq > BUFFER_SIZE // 2:
             stable_gesture_text = most_common_gesture
    
    # --- MOSTRAR O GESTO ESTABILIZADO ---
    
    # Escrever o gesto estável na tela (apenas se houver um)
    if stable_gesture_text:
        # (Fundo preto para legibilidade)
        cv2.putText(img, stable_gesture_text, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 6)
        # (Texto branco por cima)
        cv2.putText(img, stable_gesture_text, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)

    # --- MOSTRAR A ETIQUETA DA MÃO (Esquerda/Direita) ---
    
    # Mostra apenas se uma mão foi detectada (hand_label_text não está vazio)
    if hand_label_text:
        h, w, c = img.shape
        # Coloca o texto no canto superior direito
        cv2.putText(img, hand_label_text, (w - 300, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 6)
        cv2.putText(img, hand_label_text, (w - 300, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)


    # --- Atualização dos Relés REMOVIDA ---
    # for i in range(5):
    #     if dedos[i] != estado_rele_anterior[i]:
    #         rele_estado = 0 if dedos[i] == 1 else 1 
    #         rele_lines[i].set_value(rele_estado)
    #         estado_rele_anterior[i] = dedos[i]
    # --- Fim da seção REMOVIDA ---

    if frame_count % 10 == 0:
        # Imprime o valor estável e o valor "bruto" para debug
        print(f"Estavel: {stable_gesture_text}, Bruto: {current_gesture_text}, Buffer: {gesture_buffer}")
    frame_count += 1

    # Mostra a imagem em uma janela normal
    cv2.imshow("Hand Tracking", img)

    key = cv2.waitKey(1)
    if key == 27 or key == ord('q'): # Pressione ESC ou 'q' para sair
        break

    # Aguarda o tempo restante para manter 30 FPS
    elapsed = time.time() - start_time
    time_to_wait = tempo_por_frame - elapsed
    if time_to_wait > 0:
        time.sleep(time_to_wait)

# Limpeza
cap.release()
cv2.destroyAllWindows()
# --- Limpeza de GPIO REMOVIDA ---
# for rele_line in rele_lines:
#     rele_line.release()
# --- Fim da seção REMOVIDA ---