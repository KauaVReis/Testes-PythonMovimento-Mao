import cv2
import mediapipe as mp
import math
import time
from collections import Counter, deque
import numpy as np
import random
import pygame
import os

# ====================================================================
# 1. CONFIGURAÇÕES E INICIALIZAÇÃO
# ====================================================================

# --- MediaPipe ---
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=2, min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils
estilo_ponto = mp_draw.DrawingSpec(color=(0, 200, 0), thickness=-1, circle_radius=4)
estilo_linha = mp_draw.DrawingSpec(color=(20, 120, 255), thickness=2)

# --- Pygame (para som) ---
try:
    pygame.mixer.init()
    pygame.mixer.music.load("musica2.mp3")
    ponto_sound = pygame.mixer.Sound("ponto.mp3")
    pygame.mixer.music.set_volume(0.4)
    ponto_sound.set_volume(0.3)
    is_sound_enabled = True
except Exception as e:
    print(f"⚠️  Aviso: Não foi possível iniciar o som. Detalhes: {e}")
    is_sound_enabled = False

# --- Webcam ---
WIDTH, HEIGHT = 1280, 720
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
cap.set(cv2.CAP_PROP_FPS, 30)

# --- Diretórios ---
os.makedirs("fotos", exist_ok=True)

# ====================================================================
# 2. ESTADO GLOBAL DA APLICAÇÃO
# ====================================================================
app_state = {
    "current_screen": "MENU",
    "cursor_pos": np.array([WIDTH // 2, HEIGHT // 2], dtype=np.float32),
    "prev_cursor_pos": np.array([WIDTH // 2, HEIGHT // 2], dtype=np.float32),
    "click_frames": 0,
    "gesture_buffer": deque(maxlen=8),
    "stable_gesture": "",
}

# --- Estados dos Módulos ---
flappy_state = { "game_state": "START", "score": 0, "bird_y": HEIGHT // 2, "pipes": [], "start_time": 0, "last_pipe_time": 0 }
camera_state = { "app_state": "IDLE", "timer_start": 0, "flash_end": 0 }
drawing_state = { "canvas": np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8), "points": [], "color": (255, 255, 0) }

# --- Constantes ---
EMA_ALPHA = 0.4
CLICK_DISTANCE = 50
CLICK_THRESHOLD = 4

# ====================================================================
# 3. FUNÇÕES DE UTILIDADE (Helpers)
# ====================================================================

def distancia(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def is_cursor_in_rect(rect):
    x, y = int(app_state["cursor_pos"][0]), int(app_state["cursor_pos"][1])
    return rect[0] < x < rect[2] and rect[1] < y < rect[3]

def detectar_dedos_vetorial(lm_list):
    if len(lm_list) != 21: return []
    dedos = []
    def angle(p1, p2, p3):
        v1 = (p2[0] - p1[0], p2[1] - p1[1])
        v2 = (p3[0] - p2[0], p3[1] - p2[1])
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        norm = math.hypot(v1[0], v1[1]) * math.hypot(v2[0], v2[1])
        return math.acos(np.clip(dot / (norm + 1e-6), -1.0, 1.0))
    try:
        dedos.append(int(angle(lm_list[1], lm_list[2], lm_list[4]) > math.radians(160)))
        dedos.append(int(angle(lm_list[5], lm_list[6], lm_list[8]) < math.radians(40)))
        dedos.append(int(angle(lm_list[9], lm_list[10], lm_list[12]) < math.radians(40)))
        dedos.append(int(angle(lm_list[13], lm_list[14], lm_list[16]) < math.radians(40)))
        dedos.append(int(angle(lm_list[17], lm_list[18], lm_list[20]) < math.radians(40)))
    except: return [0,0,0,0,0]
    return dedos

def get_gesture_name(dedos):
    if not dedos: return ""
    if dedos == [0,0,0,0,0]: return "Punho Fechado"
    if dedos == [0,1,0,0,0]: return "Apontando"
    if dedos == [0,1,1,0,0]: return "Paz e Amor"
    if dedos == [1,1,1,1,1]: return "Mão Aberta"
    if dedos == [1,0,0,0,1]: return "Hang Loose"
    return f"{sum(dedos)} Dedo(s)"

# ====================================================================
# 4. LÓGICA DE INTERFACE (UI)
# ====================================================================
BTN_VOLTAR = (1050, 630, 1250, 700)
CALC_DISPLAY_RECT = (100, 100, 775, 175)

def draw_button(img, rect, text, bg=(60,120,190), fg=(255,255,255), alpha=0.8, shadow_offset=6):
    x1, y1, x2, y2 = rect
    cv2.rectangle(img, (x1 + shadow_offset, y1 + shadow_offset), (x2 + shadow_offset, y2 + shadow_offset), (20,20,20), -1)
    overlay = img.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), bg, -1)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
    cv2.rectangle(img, (x1, y1), (x2, y2), (230,230,230), 2)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1.1 + (x2 - x1 - 300) / 200.0
    thick = 2
    size = cv2.getTextSize(text, font, scale, thick)[0]
    tx, ty = x1 + (x2 - x1 - size[0]) // 2, y1 + (y2 - y1 + size[1]) // 2
    cv2.putText(img, text, (tx, ty), font, scale, fg, thick, cv2.LINE_AA)

def draw_main_menu(img):
    draw_button(img, (100, 150, 500, 250), "Gestos", bg=(70,130,180))
    draw_button(img, (780, 150, 1180, 250), "Desenho", bg=(80,160,110))
    draw_button(img, (100, 300, 500, 400), "Calculadora", bg=(200,120,80))
    draw_button(img, (780, 300, 1180, 400), "Flappy Dedo", bg=(255,165,0))
    draw_button(img, (440, 450, 840, 550), "Câmera", bg=(180,80,180))
    cv2.putText(img, "Selecione um Modo", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (255,255,255), 3, cv2.LINE_AA)

# ====================================================================
# 5. LÓGICA DOS MÓDULOS (TELAS)
# ====================================================================

def handle_menu_screen(click):
    if not click: return
    if is_cursor_in_rect((100, 150, 500, 250)): app_state["current_screen"] = "GESTOS"
    elif is_cursor_in_rect((780, 150, 1180, 250)):
        app_state["current_screen"] = "DESENHO"
        drawing_state["canvas"].fill(0)
        drawing_state["points"].clear()
    elif is_cursor_in_rect((100, 300, 500, 400)): app_state["current_screen"] = "CALCULADORA"
    elif is_cursor_in_rect((780, 300, 1180, 400)):
        app_state["current_screen"] = "FLAPPY"
        flappy_state.update({"game_state": "START", "score": 0, "pipes": []})
        if is_sound_enabled: pygame.mixer.music.play(-1)
    elif is_cursor_in_rect((440, 450, 840, 550)):
        app_state["current_screen"] = "FOTO"
        camera_state["app_state"] = "IDLE"

def run_gestos_screen(img, click):
    draw_button(img, BTN_VOLTAR, "Voltar")
    if click and is_cursor_in_rect(BTN_VOLTAR): app_state["current_screen"] = "MENU"
    if app_state["stable_gesture"]:
        cv2.putText(img, app_state["stable_gesture"], (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 3, (255,255,255), 5, cv2.LINE_AA)

def run_desenho_screen(img, click, dedos):
    draw_button(img, BTN_VOLTAR, "Voltar")
    if click and is_cursor_in_rect(BTN_VOLTAR): app_state["current_screen"] = "MENU"
    cv2.putText(img, "Use o gesto de 'Apontar' para desenhar", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255,255,255), 3)
    can_draw = (dedos == [0, 1, 0, 0, 0])
    pt = tuple(app_state["cursor_pos"].astype(int))
    drawing_state["points"].append(pt if can_draw else None)
    for i in range(1, len(drawing_state["points"])):
        p1 = drawing_state["points"][i - 1]
        p2 = drawing_state["points"][i]
        if p1 and p2:
            cv2.line(drawing_state["canvas"], p1, p2, drawing_state["color"], 10)
    img[drawing_state["canvas"] > 0] = drawing_state["canvas"][drawing_state["canvas"] > 0]

def run_calculadora_screen(img, click, dedos_por_mao):
    draw_button(img, BTN_VOLTAR, "Voltar")
    if click and is_cursor_in_rect(BTN_VOLTAR): app_state["current_screen"] = "MENU"

    # Desenha o visor
    x1, y1, x2, y2 = CALC_DISPLAY_RECT
    cv2.rectangle(img, (x1, y1), (x2, y2), (240, 240, 240), -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (30, 30, 30), 2)

    display_text = ""
    if len(dedos_por_mao) == 2:
        total1 = sum(dedos_por_mao[0])
        total2 = sum(dedos_por_mao[1])
        display_text = f"{total1} + {total2} = {total1 + total2}"
    elif len(dedos_por_mao) == 1:
        display_text = f"{sum(dedos_por_mao[0])}"

    cv2.putText(img, display_text, (x1 + 20, y1 + 65), cv2.FONT_HERSHEY_SIMPLEX, 2, (20,20,20), 4, cv2.LINE_AA)

def run_flappy_screen(img, click, lm_list):
    state = flappy_state
    if state["game_state"] == "START":
        cv2.putText(img, "FLAPPY DEDO", (WIDTH//2 - 270, HEIGHT//2 - 150), cv2.FONT_HERSHEY_SIMPLEX, 3, (0,255,255), 8)
        if click:
            state.update({"game_state": "PLAYING", "start_time": time.time(), "last_pipe_time": time.time(), "bird_y": HEIGHT // 2, "score": 0})
            state["pipes"] = [{"x": WIDTH + 100, "height": random.randint(200, HEIGHT-300), "gap": 220}]
    elif state["game_state"] == "PLAYING":
        if lm_list: state["bird_y"] = lm_list[8][1]
        else: state["bird_y"] += 8
        cv2.circle(img, (300, state["bird_y"]), 25, (0, 255, 255), -1)
        cv2.putText(img, f"Score: {state['score']}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (255,255,255), 5)
        if state["bird_y"] > HEIGHT - 30:
            state["game_state"] = "GAME_OVER"
            if is_sound_enabled: pygame.mixer.music.stop()
    elif state["game_state"] == "GAME_OVER":
        cv2.putText(img, "GAME OVER", (WIDTH//2-280, HEIGHT//2-100), cv2.FONT_HERSHEY_SIMPLEX, 3, (0,0,255), 8)
        if click: state["game_state"] = "START"
    draw_button(img, BTN_VOLTAR, "Voltar")
    if click and is_cursor_in_rect(BTN_VOLTAR):
        app_state["current_screen"] = "MENU"
        if is_sound_enabled: pygame.mixer.music.stop()

def run_foto_screen(img, click, frame_raw, is_hand_open):
    state = camera_state
    if state["app_state"] == "IDLE":
        cv2.putText(img, "Mao aberta para iniciar", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255,255,255), 3)
        if is_hand_open: state.update({"app_state": "ARMING", "timer_start": time.time()})
    elif state["app_state"] == "ARMING":
        remaining = 3 - int(time.time() - state["timer_start"])
        if remaining <= 0: state.update({"app_state": "POSING", "timer_start": time.time()})
    elif state["app_state"] == "POSING":
         remaining = 5 - int(time.time() - state["timer_start"])
         if remaining <= 0:
             filename = f"fotos/foto_{int(time.time())}.jpg"
             cv2.imwrite(filename, cv2.flip(frame_raw, 1))
             state.update({"app_state": "CAPTURED", "flash_end": time.time() + 0.5})
    elif state["app_state"] == "CAPTURED":
        if time.time() > state["flash_end"]: state["app_state"] = "IDLE"
        else: cv2.rectangle(img, (0,0), (WIDTH, HEIGHT), (255,255,255), -1)
    draw_button(img, BTN_VOLTAR, "Voltar")
    if click and is_cursor_in_rect(BTN_VOLTAR): app_state["current_screen"] = "MENU"

# ====================================================================
# 6. LOOP PRINCIPAL
# ====================================================================
while True:
    success, frame_raw = cap.read()
    if not success: break
    img = cv2.flip(frame_raw, 1)

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)

    primary_hand_lms = None
    dedos = []
    dedos_por_mao = []
    if results.multi_hand_landmarks:
        for hand_lms_proto in results.multi_hand_landmarks:
            lms = [(int(lm.x*WIDTH), int(lm.y*HEIGHT)) for lm in hand_lms_proto.landmark]
            dedos_por_mao.append(detectar_dedos_vetorial(lms))
            mp_draw.draw_landmarks(img, hand_lms_proto, mp_hands.HAND_CONNECTIONS, estilo_ponto, estilo_linha)

        primary_hand_lms = [(int(lm.x*WIDTH), int(lm.y*HEIGHT)) for lm in results.multi_hand_landmarks[0].landmark]
        dedos = detectar_dedos_vetorial(primary_hand_lms)
        app_state["gesture_buffer"].append(get_gesture_name(dedos))
        if len(app_state["gesture_buffer"]) == app_state["gesture_buffer"].maxlen:
            common = Counter(app_state["gesture_buffer"]).most_common(1)
            if common and common[0][1] >= 4:
                app_state["stable_gesture"] = common[0][0]

    raw_cursor = np.array(primary_hand_lms[8]) if primary_hand_lms else app_state["cursor_pos"]
    app_state["cursor_pos"] = EMA_ALPHA * raw_cursor + (1 - EMA_ALPHA) * app_state["prev_cursor_pos"]
    app_state["prev_cursor_pos"] = app_state["cursor_pos"].copy()

    click_detected = False
    if primary_hand_lms and distancia(primary_hand_lms[4], primary_hand_lms[8]) < CLICK_DISTANCE:
        app_state["click_frames"] += 1
        if app_state["click_frames"] > CLICK_THRESHOLD:
            click_detected = True
            app_state["click_frames"] = 0
    else:
        app_state["click_frames"] = 0

    screen = app_state["current_screen"]
    if screen == "MENU":
        draw_main_menu(img)
        handle_menu_screen(click_detected)
    elif screen == "GESTOS":
        run_gestos_screen(img, click_detected)
    elif screen == "DESENHO":
        run_desenho_screen(img, click_detected, dedos)
    elif screen == "CALCULADORA":
        run_calculadora_screen(img, click_detected, dedos_por_mao)
    elif screen == "FLAPPY":
        run_flappy_screen(img, click_detected, primary_hand_lms)
    elif screen == "FOTO":
        is_open = app_state["stable_gesture"] == "Mão Aberta"
        run_foto_screen(img, click_detected, frame_raw, is_open)

    cursor_int = tuple(app_state["cursor_pos"].astype(int))
    cv2.circle(img, cursor_int, 12, (0,255,0) if not click_detected else (0,0,255), -1)

    cv2.imshow("Aplicativo de Gestos", img)
    if cv2.waitKey(1) & 0xFF in [27, ord('q')]:
        break

cap.release()
cv2.destroyAllWindows()
if is_sound_enabled: pygame.mixer.quit()
