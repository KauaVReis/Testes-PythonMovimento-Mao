import cv2
import mediapipe as mp
import random
import time
import numpy as np
import pygame

# --- Som (com proteção) ---
try:
    pygame.mixer.init()
    pygame.mixer.music.load("musica2.mp3")
    pygame.mixer.music.set_volume(0.5)
    pygame.mixer.music.play(-1)
    ponto_sound = pygame.mixer.Sound("ponto.mp3")
    ponto_sound.set_volume(0.3)
except Exception as e:
    print("⚠️ Som desativado:", e)
    ponto_sound = None

# --- MediaPipe ---
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1)
mp_draw = mp.solutions.drawing_utils

# --- Webcam ---
cap = cv2.VideoCapture(0)
WIDTH, HEIGHT = 1280, 720
cap.set(3, WIDTH)
cap.set(4, HEIGHT)

# --- Parâmetros ---
bird_x = 300
bird_y = HEIGHT // 2
bird_radius = 25
bird_color = (0, 255, 255)
gravity = 7
pipe_speed_base = 18
pipe_gap_base = 230
pipe_width = 150
pipe_interval = 1600
score = 0
start_time = time.time()
game_state = "START"

pipes = []
last_pipe_time = time.time() * 1000

def create_pipe(current_gap):
    height = random.randint(100, HEIGHT - 300)
    color = (random.randint(0, 100), random.randint(150, 255), random.randint(0, 100))
    return {"x": WIDTH, "height": height, "color": color, "gap": current_gap}

def distancia(p1, p2):
    return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)**0.5

pipes.append(create_pipe(pipe_gap_base))

def detectar_pinça(lm_list):
    thumb = lm_list[4]
    index = lm_list[8]
    return distancia(thumb, index) < 60

def detectar_dedos(lm_list):
    dedos = []
    def dedo_estendido(p1, p2, p3):
        v1 = (p2[0]-p1[0], p2[1]-p1[1])
        v2 = (p3[0]-p2[0], p3[1]-p2[1])
        dot = v1[0]*v2[0] + v1[1]*v2[1]
        norm1 = (v1[0]**2 + v1[1]**2)**0.5
        norm2 = (v2[0]**2 + v2[1]**2)**0.5
        cos = dot / (norm1 * norm2 + 1e-6)
        angle = np.degrees(np.arccos(np.clip(cos, -1, 1)))
        return angle < 30
    dedos.append(int(dedo_estendido(lm_list[2], lm_list[3], lm_list[4])))
    dedos.append(int(dedo_estendido(lm_list[5], lm_list[6], lm_list[8])))
    dedos.append(int(dedo_estendido(lm_list[9], lm_list[10], lm_list[12])))
    dedos.append(int(dedo_estendido(lm_list[13], lm_list[14], lm_list[16])))
    dedos.append(int(dedo_estendido(lm_list[17], lm_list[18], lm_list[20])))
    return sum(dedos)

# --- Loop principal ---
while True:
    success, frame = cap.read()
    if not success:
        print("Erro na câmera")
        break
    frame = cv2.flip(frame, 1)

    # Filtro estético de fundo
    overlay = frame.copy()
    frame = cv2.addWeighted(overlay, 0.7, np.full_like(overlay, (255, 80, 80)), 0.3, 0)

    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)

    lm_list = []
    pinch = False
    if results.multi_hand_landmarks:
        handLms = results.multi_hand_landmarks[0]
        lm_list = [(int(lm.x * WIDTH), int(lm.y * HEIGHT)) for lm in handLms.landmark]
        mp_draw.draw_landmarks(frame, handLms, mp.solutions.hands.HAND_CONNECTIONS)
        pinch = detectar_pinça(lm_list)
        finger_count = detectar_dedos(lm_list)
    else:
        finger_count = 0

    # --- MENU INICIAL ---
    if game_state == "START":
        cv2.putText(frame, "FLAPPY DEDO", (WIDTH // 2 - 270, HEIGHT // 2 - 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 255, 255), 8)
        cv2.putText(frame, "Junte os dedos para comecar", (WIDTH // 2 - 400, HEIGHT // 2 + 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)
        cv2.rectangle(frame, (WIDTH // 2 - 180, HEIGHT // 2 + 120),
                      (WIDTH // 2 + 180, HEIGHT // 2 + 220), (0, 200, 0), -1)
        cv2.putText(frame, "START", (WIDTH // 2 - 90, HEIGHT // 2 + 190),
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)
        if pinch:
            game_state = "PLAYING"
            start_time = time.time()
            score = 0
            pipes = [create_pipe(pipe_gap_base)]
            bird_y = HEIGHT // 2

    elif game_state == "PLAYING":
        elapsed_time = time.time() - start_time
        difficulty_factor = 1 + elapsed_time / 25
        pipe_speed = min(35, int(pipe_speed_base * difficulty_factor))
        pipe_gap = int(max(180, pipe_gap_base - elapsed_time * 2 + random.randint(-15, 15)))

        # controle com dedo
        if lm_list:
            bird_y = int(lm_list[8][1])
        else:
            bird_y += gravity

        # canos
        if (time.time() * 1000) - last_pipe_time > pipe_interval:
            if not pipes or pipes[-1]["x"] < WIDTH - pipe_width * 2:
                pipes.append(create_pipe(pipe_gap))
                last_pipe_time = time.time() * 1000

        new_pipes = []
        for pipe in pipes:
            pipe["x"] -= pipe_speed
            x, h, color = pipe["x"], pipe["height"], pipe["color"]
            cv2.rectangle(frame, (x, 0), (x + pipe_width, h), color, -1)
            cv2.rectangle(frame, (x, h + pipe["gap"]), (x + pipe_width, HEIGHT), color, -1)
            if (bird_x + bird_radius > x and bird_x - bird_radius < x + pipe_width and
                (bird_y - bird_radius < h or bird_y + bird_radius > h + pipe["gap"])):
                game_state = "GAME_OVER"
            if x + pipe_width < bird_x and "counted" not in pipe:
                score += 1
                pipe["counted"] = True
                if ponto_sound:
                    ponto_sound.play()
            if x + pipe_width > 0:
                new_pipes.append(pipe)
        pipes = new_pipes

        cv2.circle(frame, (bird_x, bird_y), bird_radius, bird_color, -1)
        cv2.putText(frame, f"Pontos: {score}", (50, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)

        if bird_y - bird_radius <= 0 or bird_y + bird_radius >= HEIGHT:
            game_state = "GAME_OVER"

    elif game_state == "GAME_OVER":
        cv2.putText(frame, "GAME OVER", (WIDTH // 2 - 280, HEIGHT // 2 - 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 255), 10)
        cv2.putText(frame, f"Pontos: {score}", (WIDTH // 2 - 120, HEIGHT // 2 + 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)
        cv2.rectangle(frame, (WIDTH // 2 - 180, HEIGHT // 2 + 120),
                      (WIDTH // 2 + 180, HEIGHT // 2 + 220), (255, 255, 0), -1)
        cv2.putText(frame, "REINICIAR", (WIDTH // 2 - 150, HEIGHT // 2 + 190),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 5)
        if pinch:
            game_state = "PLAYING"
            start_time = time.time()
            score = 0
            pipes = [create_pipe(pipe_gap_base)]
            bird_y = HEIGHT // 2

    cv2.imshow("Flappy Dedo", frame)
    if cv2.waitKey(1) & 0xFF in [27, ord('q')]:
        break

pygame.mixer.music.stop()
cap.release()
cv2.destroyAllWindows()
