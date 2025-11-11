import cv2
import mediapipe as mp
# import gpiod (REMOVIDO - Específico do Raspberry Pi)
import math
import time

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
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.5)
mp_draw = mp.solutions.drawing_utils

# Estilo leve para desenhar os pontos e conexões da mão
estilo_ponto = mp_draw.DrawingSpec(color=(0, 255, 0), thickness=1, circle_radius=1)
estilo_linha = mp_draw.DrawingSpec(color=(0, 0, 255), thickness=1)

# Captura de vídeo com resolução reduzida
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
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

    if results.multi_hand_landmarks and results.multi_handedness:
        handLms = results.multi_hand_landmarks[0]
        # hand_label = results.multi_handedness[0].classification[0].label # Não usado

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

        # Mostrar a numeração dos dedos apenas se estiverem levantados
        dedo_nomes = ['1', '2', '3', '4', '5']
        pontas_dedos = [4, 8, 12, 16, 20]

        for i, idx in enumerate(pontas_dedos):
            if dedos[i]:  
                x, y = lm_list[idx]
                cv2.putText(img, dedo_nomes[i], (x - 10, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
                cv2.putText(img, dedo_nomes[i], (x - 10, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # --- Atualização dos Relés REMOVIDA ---
    # for i in range(5):
    #     if dedos[i] != estado_rele_anterior[i]:
    #         rele_estado = 0 if dedos[i] == 1 else 1 
    #         rele_lines[i].set_value(rele_estado)
    #         estado_rele_anterior[i] = dedos[i]
    # --- Fim da seção REMOVIDA ---

    if frame_count % 10 == 0:
        print("Dedos levantados:", dedos)
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