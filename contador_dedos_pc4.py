import cv2
import mediapipe as mp
import math
import time
from collections import Counter, deque
import numpy as np

# ------------------- Configurações iniciais -------------------
mp_hands = mp.solutions.hands
# max_num_hands=2 para suportar calculadora com duas mãos
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=2,
                       min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

# Estilo de desenho dos landmarks
estilo_ponto = mp_draw.DrawingSpec(color=(0, 200, 0), thickness=1, circle_radius=2)
estilo_linha = mp_draw.DrawingSpec(color=(20, 120, 255), thickness=2)

# Captura (resolução 1280x720)
cap = cv2.VideoCapture(1)
WIDTH, HEIGHT = 1280, 720
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
cap.set(cv2.CAP_PROP_FPS, 30)
fps_target = 30
tempo_por_frame = 1.0 / fps_target

# ------------------- Estado da aplicação -------------------
current_screen = "MENU"  # MENU, GESTOS, DESENHO, CALCULADORA
# Cursor (usa média exponencial para suavização)
cursor_pos = np.array((WIDTH // 2, HEIGHT // 2), dtype=np.float32)
prev_cursor_pos = cursor_pos.copy()
EMA_ALPHA = 0.45  # fator da média exponencial (0..1) -> maior = mais responsivo, menor = mais suave

# Clique por pinça (direita) - mesma lógica do seu código
click_frames = 0
CLICK_THRESHOLD = 4
CLICK_DISTANCE = 45  # ajustado para 1280x720

# Gestos
BUFFER_SIZE = 6
gesture_buffer = deque(maxlen=BUFFER_SIZE)
stable_gesture_text = ""

# Desenho
canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
draw_points = []  # lista de pontos (ou None)
current_color = (255, 255, 255)  # branco
LINE_THICKNESS = 6

# Calculadora
calc_display = ""
calc_result = None

# ------------------- UI: botões e helper drawing -------------------
# Botões (ajustados para 1280x720)
BTN_MENU_GESTOS = (100, 200, 500, 350)
BTN_MENU_DESENHO = (780, 200, 1180, 350)
BTN_MENU_CALC = (100, 450, 500, 600)
BTN_VOLTAR = (1030, 620, 1260, 700)
CALC_DISPLAY_RECT = (100, 100, 775, 175)
calc_buttons = {'CLR': (100, 575, 425, 675)}

def rect_shadowed(img, rect, bg_color=(50, 80, 120), alpha=0.7, radius=0):
    """Desenha um retângulo semi-transparente com 'sombra' por baixo."""
    x1, y1, x2, y2 = rect
    overlay = img.copy()
    # sombra deslocada
    shadow = img.copy()
    cv2.rectangle(shadow, (x1+8, y1+8), (x2+8, y2+8), (20, 20, 20), -1)
    cv2.addWeighted(shadow, 0.25, overlay, 0.75, 0, overlay)
    # retângulo principal semi-transparente
    cv2.rectangle(overlay, (x1, y1), (x2, y2), bg_color, -1)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
    # borda
    cv2.rectangle(img, (x1, y1), (x2, y2), (230, 230, 230), 2)

def draw_button(img, rect, text, bg_color=(60, 120, 190), fg_color=(255,255,255), alpha=0.82):
    x1, y1, x2, y2 = rect
    # chamo shadow + rect com transparencia
    rect_shadowed(img, rect, bg_color, alpha)
    # centraliza texto
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1.3
    thickness = 3
    text_size = cv2.getTextSize(text, font, scale, thickness)[0]
    tx = x1 + (x2 - x1 - text_size[0]) // 2
    ty = y1 + (y2 - y1 + text_size[1]) // 2
    # texto com sombra
    cv2.putText(img, text, (tx+2, ty+2), font, scale, (10,10,10), thickness+2, cv2.LINE_AA)
    cv2.putText(img, text, (tx, ty), font, scale, fg_color, thickness, cv2.LINE_AA)

def is_cursor_in_rect(cursor_xy, rect):
    x, y = int(cursor_xy[0]), int(cursor_xy[1])
    x1, y1, x2, y2 = rect
    return (x1 < x < x2) and (y1 < y < y2)

# ------------------- Detecção: dedos por ângulo vetorial -------------------
def distancia(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def detectar_dedos_vetorial(lm_list):
    """
    lm_list: lista de tuplas (x,y) com 21 landmarks (coordenadas em pixels).
    retorna lista de 5 ints (0/1) para polegar..mindinho
    """
    dedos = []
    def dedo_estendido(p1, p2, p3):
        v1 = (p2[0] - p1[0], p2[1] - p1[1])
        v2 = (p3[0] - p2[0], p3[1] - p2[1])
        dot = v1[0]*v2[0] + v1[1]*v2[1]
        norm1 = math.hypot(v1[0], v1[1])
        norm2 = math.hypot(v2[0], v2[1])
        cos_angle = dot / (norm1 * norm2 + 1e-6)
        angle = math.acos(min(1, max(-1, cos_angle)))
        return angle < math.radians(30)  # 30 graus -> considera dedo estendido

    try:
        dedos.append(int(dedo_estendido(lm_list[2], lm_list[3], lm_list[4])))   # polegar
        dedos.append(int(dedo_estendido(lm_list[5], lm_list[6], lm_list[8])))   # indicador
        dedos.append(int(dedo_estendido(lm_list[9], lm_list[10], lm_list[12]))) # medio
        dedos.append(int(dedo_estendido(lm_list[13], lm_list[14], lm_list[16])))# anelar
        dedos.append(int(dedo_estendido(lm_list[17], lm_list[18], lm_list[20])))# mindinho
    except Exception:
        dedos = [0,0,0,0,0]
    return dedos

# ------------------- Loop principal -------------------
while True:
    start_time = time.time()
    success, frame = cap.read()
    if not success:
        print("Erro ao abrir câmera.")
        break

    img = cv2.flip(frame, 1)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)

    # Reset por frame
    dedos_por_mao = []
    hand_labels = []
    click_detected = False
    # Guarda última posição do dedo indicador (para desenhar mesmo se mediapipe oscilar)
    last_index_point = None

    # Se houver detecções
    if results.multi_hand_landmarks and results.multi_handedness:
        # iterar por cada mão detectada (até 2)
        for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
            label = handedness.classification[0].label  # "Left" ou "Right"
            lm_list = []
            for lm in hand_landmarks.landmark:
                lm_list.append((int(lm.x * WIDTH), int(lm.y * HEIGHT)))
            dedos = detectar_dedos_vetorial(lm_list)
            dedos_por_mao.append(dedos)
            hand_labels.append(label)

            # desenha landmarks estilizados
            mp_draw.draw_landmarks(img, hand_landmarks, mp_hands.HAND_CONNECTIONS, estilo_ponto, estilo_linha)

        # Determinar qual mão usar para cursor/clique: prioriza direita (como no seu código original)
        right_index = None
        for i, lab in enumerate(hand_labels):
            if lab == "Right":
                right_index = i
                break
        # se não achar direita, usa a primeira mão como fallback
        primary_index = right_index if right_index is not None else 0

        # Pegamos o ponto 8 (ponta do indicador) da mão primária para o cursor
        try:
            primary_hand_landmarks = results.multi_hand_landmarks[primary_index]
            lm_list_primary = [(int(lm.x * WIDTH), int(lm.y * HEIGHT)) for lm in primary_hand_landmarks.landmark]
            raw_cursor = np.array(lm_list_primary[8], dtype=np.float32)
            last_index_point = tuple(lm_list_primary[8])
        except Exception:
            raw_cursor = cursor_pos.copy()
    else:
        raw_cursor = cursor_pos.copy()

    # ------------------- Suavização do cursor (EMA) -------------------
    # cursor_pos e prev_cursor_pos são vetores float
    cursor_pos = EMA_ALPHA * raw_cursor + (1 - EMA_ALPHA) * prev_cursor_pos
    prev_cursor_pos = cursor_pos.copy()

    # ------------------- Detecção de clique (pinça) usando a mão primária (direita preferencial) ---
    if results.multi_hand_landmarks and results.multi_handedness:
        # tenta pegar landmarks da mão direita (ou primeira como fallback)
        try:
            # mesmo index primary_index definido acima (recalc para segurança)
            right_index = None
            for i, hand_info in enumerate(results.multi_handedness):
                if hand_info.classification[0].label == "Right":
                    right_index = i
                    break
            primary_index = right_index if right_index is not None else 0
            hand_lm = results.multi_hand_landmarks[primary_index]
            lm_list_for_click = [(int(lm.x * WIDTH), int(lm.y * HEIGHT)) for lm in hand_lm.landmark]
            pinch_dist = distancia(lm_list_for_click[4], lm_list_for_click[8])  # polegar x indicador
            if pinch_dist < CLICK_DISTANCE:
                click_frames += 1
            else:
                click_frames = 0
            if click_frames > CLICK_THRESHOLD:
                click_detected = True
                click_frames = 0
        except Exception:
            click_frames = 0
            click_detected = False
    else:
        click_frames = 0

    # ------------------- Maquina de telas -------------------
    # desenha o menu / telas com a UI melhorada
    if current_screen == "MENU":
        draw_button(img, BTN_MENU_GESTOS, "Gestos", bg_color=(70,130,180))
        draw_button(img, BTN_MENU_DESENHO, "Desenho", bg_color=(80,160,110))
        draw_button(img, BTN_MENU_CALC, "Calculadora", bg_color=(200,120,80))

        cv2.putText(img, "Use o indicador para apontar", (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (240,240,240), 2, cv2.LINE_AA)
        cv2.putText(img, "Faça 'pinça' para clicar (polegar + indicador)", (50, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (220,220,220), 2, cv2.LINE_AA)

        if click_detected:
            if is_cursor_in_rect(cursor_pos, BTN_MENU_GESTOS):
                current_screen = "GESTOS"
            elif is_cursor_in_rect(cursor_pos, BTN_MENU_DESENHO):
                current_screen = "DESENHO"
                canvas.fill(0)
                draw_points.clear()
                gesture_buffer.clear()
            elif is_cursor_in_rect(cursor_pos, BTN_MENU_CALC):
                current_screen = "CALCULADORA"
                calc_display = ""
                calc_result = None
                gesture_buffer.clear()

    elif current_screen == "GESTOS":
        draw_button(img, BTN_VOLTAR, "Voltar", bg_color=(140, 80, 160))
        # Usamos a mão primária (se disponível) para identificar gestos como no seu código original
        if len(dedos_por_mao) > 0:
            dedos = dedos_por_mao[0]
            # lógica original de mapeamento de gestos
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
                current_gesture_text = f"Dedos: {dedos.count(1)}"

            # filtro de estabilização
            gesture_buffer.append(current_gesture_text)
            if len(gesture_buffer) == BUFFER_SIZE:
                count_data = Counter(gesture_buffer)
                most_common_gesture, freq = count_data.most_common(1)[0]
                if freq > BUFFER_SIZE // 2:
                    stable_gesture_text = most_common_gesture

        # desenhar texto estabilizado
        if stable_gesture_text:
            cv2.putText(img, stable_gesture_text, (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (10,10,10), 8, cv2.LINE_AA)
            cv2.putText(img, stable_gesture_text, (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (240,240,240), 3, cv2.LINE_AA)

        # etiqueta de qual mão foi detectada (se houver)
        if len(hand_labels) > 0:
            label_text = "Mãos: " + ", ".join(hand_labels)
            cv2.putText(img, label_text, (WIDTH - 520, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (10,10,10), 6, cv2.LINE_AA)
            cv2.putText(img, label_text, (WIDTH - 520, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (240,240,240), 2, cv2.LINE_AA)

        if click_detected and is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
            current_screen = "MENU"
            stable_gesture_text = ""
            gesture_buffer.clear()

    elif current_screen == "DESENHO":
        draw_button(img, BTN_VOLTAR, "Voltar", bg_color=(100, 180, 160))
        cv2.putText(img, "Levante o dedo indicador para desenhar", (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (240,240,240), 2, cv2.LINE_AA)
        cv2.putText(img, "Pinça (direita) para clicar/voltar", (50, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (220,220,220), 2, cv2.LINE_AA)

        # Gesto de desenhar: indicador levantado sozinho (primeira mão detectada)
        can_draw = False
        if len(dedos_por_mao) > 0:
            # preferir a mão primária para desenhar (se a primeira mão tiver o gesto)
            dedos_first = dedos_por_mao[0]
            if dedos_first == [0, 1, 0, 0, 0]:
                can_draw = True

        if can_draw:
            # adiciona o ponto suavizado como inteiro
            pt = (int(cursor_pos[0]), int(cursor_pos[1]))
            draw_points.append(pt)
        else:
            draw_points.append(None)

        # Interpolação e desenho contínuo com espessura grande para suavizar
        for i in range(1, len(draw_points)):
            p0 = draw_points[i-1]
            p1 = draw_points[i]
            if p0 is not None and p1 is not None:
                # se a distância for grande, interpolar em passos para evitar "linha quebrada"
                dist = distancia(p0, p1)
                steps = max(1, int(dist // 5))
                for s in range(1, steps+1):
                    t = s / float(steps)
                    x = int(p0[0] + (p1[0] - p0[0]) * t)
                    y = int(p0[1] + (p1[1] - p0[1]) * t)
                    # desenho espesso (pincel)
                    cv2.circle(canvas, (x, y), LINE_THICKNESS//2, current_color, -1)
            # se não houver ponto anterior, nada a fazer

        # Merge canvas sobre a imagem com preservação dos pixels desenhados
        img_gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(img_gray, 1, 255, cv2.THRESH_BINARY)
        mask_inv = cv2.bitwise_not(mask)
        img_bg = cv2.bitwise_and(img, img, mask=mask_inv)
        img_fg = cv2.bitwise_and(canvas, canvas, mask=mask)
        img = cv2.add(img_bg, img_fg)

        if click_detected and is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
            current_screen = "MENU"
            # opcional: limpar canvas quando volta? mantém como estava no seu código original
            # canvas.fill(0)
            # draw_points.clear()

    elif current_screen == "CALCULADORA":
        draw_button(img, BTN_VOLTAR, "Voltar", bg_color=(180,120,90))
        # visor
        x1, y1, x2, y2 = CALC_DISPLAY_RECT
        overlay = img.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (240, 240, 240), -1)
        cv2.addWeighted(overlay, 0.9, img, 0.1, 0, img)
        cv2.rectangle(img, (x1, y1), (x2, y2), (30, 30, 30), 2)

        # lógica: se houver 2 mãos detectadas, soma o total de dedos de cada mão
        if len(dedos_por_mao) == 2:
            total1 = sum(dedos_por_mao[0])
            total2 = sum(dedos_por_mao[1])
            calc_display = f"{total1} + {total2}"
            calc_result = total1 + total2
        elif len(dedos_por_mao) == 1:
            total1 = sum(dedos_por_mao[0])
            calc_display = f"{total1}"
            calc_result = total1
        else:
            calc_display = ""
            calc_result = None

        # escreve no visor
        display_text = calc_display
        if calc_result is not None and calc_display != "":
            display_text = f"{calc_display} = {calc_result}"
        cv2.putText(img, display_text, (x1 + 14, y1 + 70), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (20,20,20), 4, cv2.LINE_AA)

        # botão CLR
        draw_button(img, calc_buttons['CLR'], "CLR", bg_color=(200,80,120))
        if click_detected and is_cursor_in_rect(cursor_pos, calc_buttons['CLR']):
            calc_display = ""
            calc_result = None

        if click_detected and is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
            current_screen = "MENU"

    # ------------------- Desenhar cursor (indicador) -------------------
    # se houver uma mão/indicador, desenha círculo suavizado; caso contrário, desenha posição atual
    cursor_int = (int(cursor_pos[0]), int(cursor_pos[1]))
    # cor depende se estamos em estado de 'click_frames' (apertando)
    cursor_color = (0, 220, 0) if click_frames == 0 else (0, 80, 200)
    cv2.circle(img, cursor_int, 10, cursor_color, -1)
    cv2.circle(img, cursor_int, 10, (255,255,255), 2)

    # mostrar indicador guia (pequena cruz)
    cv2.line(img, (cursor_int[0]-12, cursor_int[1]), (cursor_int[0]+12, cursor_int[1]), (255,255,255), 1)
    cv2.line(img, (cursor_int[0], cursor_int[1]-12), (cursor_int[0], cursor_int[1]+12), (255,255,255), 1)

    # FPS simples (opcional)
    elapsed = time.time() - start_time
    fps = 1.0 / (elapsed + 1e-6)
    cv2.putText(img, f"FPS: {int(fps)}", (WIDTH - 180, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220,220,220), 2, cv2.LINE_AA)

    # Exibe a imagem final
    cv2.imshow("Hand Tracking - Smart UI", img)
    key = cv2.waitKey(1)
    if key == 27 or key == ord('q'):
        break

    # manter ~30 FPS
    elapsed_total = time.time() - start_time
    sleep_time = tempo_por_frame - elapsed_total
    if sleep_time > 0:
        time.sleep(sleep_time)

# limpeza
cap.release()
cv2.destroyAllWindows()
