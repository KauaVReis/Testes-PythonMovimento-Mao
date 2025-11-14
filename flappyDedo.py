import cv2
import mediapipe as mp
import math
import time
from collections import Counter, deque
import numpy as np
import os
import random
import shutil # Importado para copiar arquivos de imagem

# --- Tenta importar o conector MySQL ---
try:
    import mysql.connector
    db_ok = True
except ImportError:
    print("----------------------------------------------------")
    print("AVISO: mysql-connector-python nao encontrado.")
    print("O app vai rodar, mas NAO VAI SALVAR scores no banco.")
    print("Para instalar, rode: python -m pip install mysql-connector-python")
    print("----------------------------------------------------")
    db_ok = False

# --- Tenta importar e inicializar o Pygame (para o jogo) ---
try:
    import pygame
    pygame.mixer.init()
    
    # --- MUDANÇA: Caminho dos Assets ---
    ASSETS_PATH = "assets"
    pygame.mixer.music.load(os.path.join(ASSETS_PATH, "musica2.mp3")) # Fundo do Jogo
    pygame.mixer.music.set_volume(0.3)
    ponto_sound = pygame.mixer.Sound(os.path.join(ASSETS_PATH, "ponto.mp3")) # Som de ponto
    # --- Fim da mudança ---
    
    ponto_sound.set_volume(0.3)
    pygame_ok = True
except Exception as e:
    print(f"Aviso: Nao foi possivel carregar arquivos de som (assets/musica2.mp3, assets/ponto.mp3): {e}")
    print("O jogo funcionara sem som.")
    pygame_ok = True # O jogo roda, mas sem som
    ponto_sound = None
    
except ImportError:
    print("----------------------------------------------------")
    print("AVISO: Pygame nao encontrado. O Jogo nao funcionara.")
    print("Para instalar, rode: python -m pip install pygame")
    print("----------------------------------------------------")
    pygame_ok = False
    ponto_sound = None


# ------------------- Configurações iniciais -------------------
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=2,
                       min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

# Estilo de desenho
estilo_ponto = mp_draw.DrawingSpec(color=(0, 200, 0), thickness=1, circle_radius=2)
estilo_linha = mp_draw.DrawingSpec(color=(20, 120, 255), thickness=2)

# Captura (1280x720)
cap = cv2.VideoCapture(0)
WIDTH, HEIGHT = 1280, 720
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
cap.set(cv2.CAP_PROP_FPS, 30)
fps_target = 30
tempo_por_frame = 1.0 / fps_target

# Pasta local (para TODAS as fotos)
# O PHP vai ler direto desta pasta
output_folder = "fotos" 
os.makedirs(output_folder, exist_ok=True)


# ------------------- Configuração do Banco de Dados -------------------
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root', 
    'password': '', # Senha vazia (padrão XAMPP/WAMP)
    'database': 'flappy_game_db'
}

def insert_score_to_db(score, image_filename):
    """
    Insere o score e o NOME do arquivo no banco de dados.
    """
    if not db_ok:
        print(f"Score {score} nao salvo (mysql-connector nao instalado).")
        return

    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
        cursor = cnx.cursor()
        
        sql = "INSERT INTO highscores (score, image_path) VALUES (%s, %s)"
        data = (score, image_filename)
        
        cursor.execute(sql, data)
        cnx.commit()
        
        print(f"✅ SUCESSO! Score {score} e imagem {image_filename} salvos no banco de dados.")

    except mysql.connector.Error as err:
        print(f"❌ ERRO FATAL AO INSERIR NO MYSQL: {err}")
        print("Verifique se o XAMPP (MySQL) esta rodando e se o banco/tabela existem.")
    finally:
        if 'cnx' in locals() and cnx.is_connected():
            cursor.close()
            cnx.close()
# --- Fim da Configuração do DB ---


# ------------------- Estado da aplicação (Geral) -------------------
current_screen = "MENU"
cursor_pos = (WIDTH // 2, HEIGHT // 2)
last_cursor_pos = (WIDTH // 2, HEIGHT // 2)
EMA_ALPHA = 0.3 
click_frames = 0
CLICK_THRESHOLD = 3
CLICK_DISTANCE = 50

# Estado: Gestos
BUFFER_SIZE = 5
gesture_buffer = deque(maxlen=BUFFER_SIZE)
stable_gesture_text = ""

# Estado: Desenho
canvas = np.ones((HEIGHT, WIDTH, 3), dtype=np.uint8) * 255 # Canvas Branco
last_draw_point = None
current_color = (0, 0, 0)  # Padrão Preto
current_thickness = 12

# Estado: Câmera
photo_app_state = "IDLE"
photo_timer_start_time = 0
photo_flash_start_time = 0
# --- MUDANÇA: Lógica de 3s para armar + 3s para pose ---
TIMER_ARM_HOLD = 3 # 3 segundos segurando a mão
TIMER_POSING = 3   # 3 segundos para a pose
# --- Fim da mudança ---

# Estado: Jogo
game_state = "START"
game_bird_y = HEIGHT // 2
BIRD_WIDTH, BIRD_HEIGHT = 85, 60
BIRD_X_POS = (WIDTH // 2) - 150
game_pipes = []
game_pipe_speed = 20
game_pipe_gap = 220
game_pipe_width = 150 # (Será atualizado pelos sprites)
game_last_pipe_time = 0
game_pipe_interval = 1.3
game_score = 0
game_start_time = 0

# ------------------- Carregar Sprites (Imagens) -------------------
if 'ASSETS_PATH' not in locals(): ASSETS_PATH = "assets"
try:
    sprite_passaro = cv2.imread(os.path.join(ASSETS_PATH, "passaro.png"), -1)
    sprite_cano_cima = cv2.imread(os.path.join(ASSETS_PATH, "pipe_cima.png"), -1)
    sprite_cano_baixo = cv2.imread(os.path.join(ASSETS_PATH, "pipe_baixo.png"), -1)

    if sprite_passaro is None or sprite_cano_cima is None or sprite_cano_baixo is None:
        raise IOError("Nao foi possivel carregar um ou mais arquivos de sprite (passaro.png, pipe_cima.png, pipe_baixo.png)")
    
    # Redimensiona o pássaro
    sprite_passaro = cv2.resize(sprite_passaro, (BIRD_WIDTH, BIRD_HEIGHT))
    
    # Força o redimensionamento dos canos
    PIPE_TARGET_WIDTH = 150  # Largura do cano
    PIPE_TARGET_HEIGHT = 600 # Altura do cano
    sprite_cano_cima = cv2.resize(sprite_cano_cima, (PIPE_TARGET_WIDTH, PIPE_TARGET_HEIGHT))
    sprite_cano_baixo = cv2.resize(sprite_cano_baixo, (PIPE_TARGET_WIDTH, PIPE_TARGET_HEIGHT))
    game_pipe_width, PIPE_HEIGHT = PIPE_TARGET_WIDTH, PIPE_TARGET_HEIGHT

    sprites_ok = True
    print("Sprites do jogo (passaro, canos) carregados com sucesso!")

except Exception as e:
    print(f"----------------------------------------------------")
    print(f"AVISO: Nao foi possivel carregar os sprites: {e}")
    print(f"O jogo vai rodar no 'modo classico' (com circulos e retangulos).")
    print(f"Verifique se os arquivos 'passaro.png', 'pipe_cima.png' e 'pipe_baixo.png' estao na pasta 'assets'.")
    print(f"----------------------------------------------------")
    sprites_ok = False
    BIRD_WIDTH, BIRD_HEIGHT = 50, 50 
    game_pipe_width = 120 

# --- MUDANÇA: Carregar Moldura do Evento ---
try:
    sprite_moldura = cv2.imread(os.path.join(ASSETS_PATH, "moldura_evento.png"), -1)
    if sprite_moldura is None:
        raise IOError("Arquivo moldura_evento.png nao encontrado")
    
    # Garante que a moldura tenha o tamanho exato da tela
    if sprite_moldura.shape[0] != HEIGHT or sprite_moldura.shape[1] != WIDTH:
        print(f"Aviso: Redimensionando 'moldura_evento.png' de {sprite_moldura.shape} para {(HEIGHT, WIDTH)}.")
        sprite_moldura = cv2.resize(sprite_moldura, (WIDTH, HEIGHT))
        
    frame_ok = True
    print("Moldura do evento carregada com sucesso!")

except Exception as e:
    print(f"----------------------------------------------------")
    print(f"AVISO: Nao foi possivel carregar a moldura do evento: {e}")
    print("As fotos serao salvas SEM moldura.")
    print(f"Verifique se 'moldura_evento.png' esta na pasta 'assets'.")
    print(f"----------------------------------------------------")
    frame_ok = False
# --- Fim da Mudança ---

# ------------------- Funções de Detecção -------------------
def distancia(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def detectar_dedos_vetorial(lm_list):
    dedos = []
    def dedo_estendido(p1, p2, p3):
        v1 = (p2[0] - p1[0], p2[1] - p1[1])
        v2 = (p3[0] - p2[0], p3[1] - p2[1])
        dot = v1[0]*v2[0] + v1[1]*v2[1]
        norm1 = math.hypot(v1[0], v1[1])
        norm2 = math.hypot(v2[0], v2[1])
        cos_angle = dot / (norm1 * norm2 + 1e-6)
        angle = math.acos(min(1, max(-1, cos_angle)))
        return angle < math.radians(30)

    try:
        dedos.append(int(dedo_estendido(lm_list[2], lm_list[3], lm_list[4])))   # polegar
        dedos.append(int(dedo_estendido(lm_list[5], lm_list[6], lm_list[8])))   # indicador
        dedos.append(int(dedo_estendido(lm_list[9], lm_list[10], lm_list[12]))) # medio
        dedos.append(int(dedo_estendido(lm_list[13], lm_list[14], lm_list[16])))# anelar
        dedos.append(int(dedo_estendido(lm_list[17], lm_list[18], lm_list[20])))# mindinho
    except Exception:
        dedos = [0,0,0,0,0]
    return dedos

# ------------------- Funções de UI (Botões) -------------------
BTN_MENU_GESTOS = (100, 150, 550, 300)
BTN_MENU_DESENHO = (730, 150, 1180, 300)
BTN_MENU_FOTO = (100, 400, 550, 550)
BTN_MENU_JOGO = (730, 400, 1180, 550)
BTN_VOLTAR = (1030, 620, 1260, 700)
BTN_GAME_RESTART = (WIDTH // 2 - 200, HEIGHT // 2 + 100, WIDTH // 2 + 200, HEIGHT // 2 + 200)

# Paleta de Desenho
PALETTE_X_START = 1080
PALETTE_X_END = 1260
BTN_DRAW_RED = (PALETTE_X_START, 20, PALETTE_X_END, 70)
BTN_DRAW_GREEN = (PALETTE_X_START, 80, PALETTE_X_END, 130)
BTN_DRAW_BLUE = (PALETTE_X_START, 140, PALETTE_X_END, 190)
BTN_DRAW_YELLOW = (PALETTE_X_START, 200, PALETTE_X_END, 250)
BTN_DRAW_BLACK = (PALETTE_X_START, 260, PALETTE_X_END, 310)
BTN_DRAW_ERASER = (PALETTE_X_START, 320, PALETTE_X_END, 370)
BTN_DRAW_CLEAR = (PALETTE_X_START, 380, PALETTE_X_END, 430)
BTN_DRAW_PHOTO = (PALETTE_X_START, 440, PALETTE_X_END, 490)


def draw_button(img, rect, text, bg_color=(60, 120, 190), is_selected=False):
    """Desenha um botão básico na tela"""
    x1, y1, x2, y2 = rect
    cv2.rectangle(img, (x1, y1), (x2, y2), bg_color, -1)
    
    border_color = (0, 255, 255) if is_selected else (255, 255, 255)
    border_thickness = 4 if is_selected else 3
    cv2.rectangle(img, (x1, y1), (x2, y2), border_color, border_thickness) # Borda
    
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1.3
    thickness = 3
    text_size = cv2.getTextSize(text, font, scale, thickness)[0]
    if text_size[0] > (x2 - x1 - 20): 
        scale = 1.0 
        text_size = cv2.getTextSize(text, font, scale, thickness)[0]
        
    tx = x1 + (x2 - x1 - text_size[0]) // 2
    ty = y1 + (y2 - y1 + text_size[1]) // 2
    cv2.putText(img, text, (tx, ty), font, scale, (255, 255, 255), thickness)

def is_cursor_in_rect(cursor_xy, rect):
    x, y = cursor_xy
    x1, y1, x2, y2 = rect
    return x1 < x < x2 and y1 < y < y2

# ------------------- Funções de Sprite -------------------
def draw_sprite(background, sprite, x, y):
    """
    Desenha um sprite (imagem PNG com alfa) sobre o background.
    x, y é a posição do canto SUPERIOR ESQUERDO do sprite.
    """
    try:
        h, w, channels = sprite.shape
    except ValueError:
        return 
        
    x, y = int(x), int(y) 

    if channels < 4:
        return 

    alpha = sprite[:, :, 3] / 255.0 
    
    y1, y2 = max(0, y), min(HEIGHT, y + h)
    x1, x2 = max(0, x), min(WIDTH, x + w)
    
    sprite_y1, sprite_y2 = max(0, -y), min(h, HEIGHT - y)
    sprite_x1, sprite_x2 = max(0, -x), min(w, WIDTH - x)

    if y1 >= y2 or x1 >= x2 or sprite_y1 >= sprite_y2 or sprite_x1 >= sprite_x2:
        return

    roi = background[y1:y2, x1:x2]
    sprite_cut = sprite[sprite_y1:sprite_y2, sprite_x1:sprite_x2]
    alpha_cut = alpha[sprite_y1:sprite_y2, sprite_x1:sprite_x2]
    
    alpha_3d = cv2.merge([alpha_cut, alpha_cut, alpha_cut])
    alpha_inv_3d = 1.0 - alpha_3d

    roi_bg = cv2.multiply(alpha_inv_3d, roi.astype(float))
    sprite_fg = cv2.multiply(alpha_3d, sprite_cut[:,:,:3].astype(float))
    
    background[y1:y2, x1:x2] = cv2.add(roi_bg, sprite_fg).astype(np.uint8)

def check_collision(bird_rect, pipe_rect):
    """Verifica colisão de Bounding Box (AABB)"""
    bx1, by1, bx2, by2 = bird_rect
    px1, py1, px2, py2 = pipe_rect
    
    if bx1 > px2 or bx2 < px1: return False
    if by1 > py2 or by2 < py1: return False
    return True
# --- Fim das funções de Sprite ---

# ------------------- Loop principal -------------------
while True:
    start_time_frame = time.time()
    
    success, img_raw = cap.read()
    if not success:
        print("Erro ao abrir câmera.")
        break

    img = cv2.flip(img_raw, 1)
    
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)

    click_detected = False
    pinch_dist = 999
    is_pinching = False
    lm_list_nav = None
    dedos_nav = [0,0,0,0,0]
    nav_hand_index = -1
    
    # --- Lógica de Detecção de Mão (Mão de Navegação) ---
    if results.multi_hand_landmarks and results.multi_handedness:
        for i, hand_info in enumerate(results.multi_handedness):
            if hand_info.classification[0].label == "Right":
                nav_hand_index = i
                break
        if nav_hand_index == -1:
            nav_hand_index = 0
            
        handLms_nav = results.multi_hand_landmarks[nav_hand_index]
        
        if not (current_screen == "DESENHO" and photo_app_state != "IDLE"):
             mp_draw.draw_landmarks(img, handLms_nav, mp_hands.HAND_CONNECTIONS, estilo_ponto, estilo_linha)

        lm_list_nav = []
        for lm in handLms_nav.landmark:
            lm_list_nav.append((int(lm.x * WIDTH), int(lm.y * HEIGHT)))
        
        raw_cursor_pos = lm_list_nav[8] # Ponta do indicador
        cursor_pos = (int(EMA_ALPHA * raw_cursor_pos[0] + (1 - EMA_ALPHA) * last_cursor_pos[0]),
                      int(EMA_ALPHA * raw_cursor_pos[1] + (1 - EMA_ALPHA) * last_cursor_pos[1]))
        last_cursor_pos = cursor_pos
        
        dedos_nav = detectar_dedos_vetorial(lm_list_nav)
        
        # Trava de clique (pinça)
        if photo_app_state == "IDLE": 
            pinch_dist = distancia(lm_list_nav[4], lm_list_nav[8]) 
            is_pinching = (pinch_dist < CLICK_DISTANCE)
            
            if is_pinching:
                click_frames += 1
            else:
                click_frames = 0 
                
            if click_frames == CLICK_THRESHOLD: 
                click_detected = True 
                print("CLICK DETECTED")

    else:
        click_frames = 0
        
    # --- Fim da Lógica de Detecção ---


    # ----------------------------------------------------
    # --- MÁQUINA DE ESTADOS (RENDERIZAÇÃO DE TELAS) ---
    # ----------------------------------------------------

    if current_screen == "MENU":
        cv2.putText(img, "GESTURE SUITE", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0,0,0), 8)
        cv2.putText(img, "GESTURE SUITE", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (255, 255, 255), 3)

        draw_button(img, BTN_MENU_GESTOS, "Gestos")
        draw_button(img, BTN_MENU_DESENHO, "Desenho")
        draw_button(img, BTN_MENU_FOTO, "Camera")
        
        if pygame_ok and sprites_ok:
            draw_button(img, BTN_MENU_JOGO, "Jogo")
        else:
            draw_button(img, BTN_MENU_JOGO, "Jogo (OFF)", bg_color=(100,100,100)) 

        if click_detected:
            if is_cursor_in_rect(cursor_pos, BTN_MENU_GESTOS):
                current_screen = "GESTOS"
            
            elif is_cursor_in_rect(cursor_pos, BTN_MENU_DESENHO):
                current_screen = "DESENHO"
                canvas.fill(255) # Limpa com BRANCO
                last_draw_point = None
                photo_app_state = "IDLE" 
            
            elif is_cursor_in_rect(cursor_pos, BTN_MENU_FOTO):
                current_screen = "FOTO"
                photo_app_state = "IDLE"
                photo_timer_start_time = 0 
            
            elif is_cursor_in_rect(cursor_pos, BTN_MENU_JOGO) and pygame_ok and sprites_ok:
                current_screen = "JOGO"
                game_state = "START"
                game_bird_y = HEIGHT // 2
                game_pipes = []
                game_score = 0
                game_start_time = time.time()
                if pygame_ok and pygame.mixer.music.get_busy() == False:
                    pygame.mixer.music.play(-1) 

    # --- TELA DE GESTOS ---
    elif current_screen == "GESTOS":
        draw_button(img, BTN_VOLTAR, "Voltar")

        total_fingers = 0
        if results.multi_hand_landmarks:
            for i, handLms in enumerate(results.multi_hand_landmarks):
                lm_list = []
                for lm in handLms.landmark:
                    lm_list.append((int(lm.x * WIDTH), int(lm.y * HEIGHT)))
                
                dedos = detectar_dedos_vetorial(lm_list)
                total_fingers += sum(dedos)
                
                if i != nav_hand_index:
                     mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS, estilo_ponto, estilo_linha)

        if dedos_nav == [0, 0, 0, 0, 0]: current_gesture_text = "Punho Fechado"
        elif dedos_nav == [0, 1, 0, 0, 0]: current_gesture_text = "Apontando (1)"
        elif dedos_nav == [0, 1, 1, 0, 0]: current_gesture_text = "Paz (2)"
        elif dedos_nav == [1, 0, 0, 0, 0]: current_gesture_text = "Joia"
        elif dedos_nav == [1, 1, 1, 1, 1]: current_gesture_text = "Mao Aberta (5)"
        else: current_gesture_text = ""
        
        gesture_buffer.append(current_gesture_text)
        if len(gesture_buffer) == BUFFER_SIZE:
            count_data = Counter(gesture_buffer)
            if count_data: 
                most_common = count_data.most_common(1)[0]
                if most_common[1] > BUFFER_SIZE // 2: 
                    stable_gesture_text = most_common[0]

        if stable_gesture_text:
            cv2.putText(img, stable_gesture_text, (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0,0,0), 8)
            cv2.putText(img, stable_gesture_text, (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (255, 255, 255), 3)

        cv2.putText(img, f"Total de Dedos: {total_fingers}", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0,0,0), 8)
        cv2.putText(img, f"Total de Dedos: {total_fingers}", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 3)

        if click_detected and is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
            current_screen = "MENU"
            gesture_buffer.clear()
            stable_gesture_text = ""

    # --- TELA DE DESENHO ---
    elif current_screen == "DESENHO":
        
        overlay_text = ""
        countdown_text = ""
        
        # Lógica de máscara para canvas BRANCO
        img_gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(img_gray, 254, 255, cv2.THRESH_BINARY_INV) 

        img_bg = cv2.bitwise_and(img, img, mask=cv2.bitwise_not(mask))
        img_fg = cv2.bitwise_and(canvas, canvas, mask=mask)
        img_with_drawing = cv2.add(img_bg, img_fg)
        
        img_display = img_with_drawing.copy()

        # Lógica de estado da Câmera
        if photo_app_state == "ARMING": 
            time_elapsed = time.time() - photo_timer_start_time
            countdown_value = 3 - int(time_elapsed)
            
            if countdown_value > 0:
                countdown_text = str(countdown_value)
                overlay_text = "Prepare-se..."
            else:
                photo_app_state = "POSING"
                photo_timer_start_time = time.time()
                print("Armado! Faca a pose...")
        
        elif photo_app_state == "POSING": 
            time_elapsed = time.time() - photo_timer_start_time
            countdown_value = TIMER_POSING - int(time_elapsed)
            
            if countdown_value > 0:
                countdown_text = str(countdown_value)
                overlay_text = "Faca a pose!"
            else:
                # --- MUDANÇA V2: Salvar foto do Desenho ---
                filename_base = f"foto_desenho_{int(time.time())}.jpg"
                
                # --- MUDANÇA: Aplicar Moldura ---
                imagem_final = img_with_drawing.copy() # Pega a imagem com desenho
                if frame_ok:
                    draw_sprite(imagem_final, sprite_moldura, 0, 0)
                # --- Fim da mudança ---

                local_path = os.path.join(output_folder, filename_base)
                cv2.imwrite(local_path, imagem_final) # Salva a imagem com moldura
                print(f"Foto Desenho salva em: {local_path}")
                
                # Envia para o Banco de Dados (com score 0)
                insert_score_to_db(0, filename_base)
                # --- Fim da Mudança V2 ---
                
                photo_app_state = "CAPTURED"
                photo_flash_start_time = time.time()
        
        if photo_app_state == "CAPTURED":
            overlay_text = "FOTO CAPTURADA!"
            if time.time() - photo_flash_start_time < 0.5:
                cv2.rectangle(img_display, (0, 0), (WIDTH, HEIGHT), (255, 255, 255), -1)
            else:
                photo_app_state = "IDLE" 
                
        # Desenha a paleta de cores (na img_display)
        draw_button(img_display, BTN_DRAW_RED, "Vermelho", bg_color=(0,0,255), is_selected=(current_color == (0,0,255)))
        draw_button(img_display, BTN_DRAW_GREEN, "Verde", bg_color=(0,255,0), is_selected=(current_color == (0,255,0)))
        draw_button(img_display, BTN_DRAW_BLUE, "Azul", bg_color=(255,0,0), is_selected=(current_color == (255,0,0)))
        draw_button(img_display, BTN_DRAW_YELLOW, "Amarelo", bg_color=(0,255,255), is_selected=(current_color == (0,255,255)))
        draw_button(img_display, BTN_DRAW_BLACK, "Preto", bg_color=(50,50,50), is_selected=(current_color == (0,0,0) and current_thickness == 12))
        draw_button(img_display, BTN_DRAW_ERASER, "Borracha", bg_color=(200,200,200), is_selected=(current_color == (255,255,255)))
        draw_button(img_display, BTN_DRAW_CLEAR, "Limpar")
        draw_button(img_display, BTN_DRAW_PHOTO, "Foto") 
        draw_button(img_display, BTN_VOLTAR, "Voltar")
        
        # Lógica de clique (só funciona se não estiver tirando foto)
        if click_detected and photo_app_state == "IDLE":
            if is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
                current_screen = "MENU"
            
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_RED):
                current_color = (0, 0, 255) # BGR
                current_thickness = 12
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_GREEN):
                current_color = (0, 255, 0)
                current_thickness = 12
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_BLUE):
                current_color = (255, 0, 0)
                current_thickness = 12
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_YELLOW):
                current_color = (0, 255, 255)
                current_thickness = 12
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_BLACK):
                current_color = (0, 0, 0) # PRETO
                current_thickness = 12
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_ERASER):
                current_color = (255, 255, 255) # BRANCO
                current_thickness = 40 
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_CLEAR):
                canvas.fill(255) # BRANCO
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_PHOTO):
                print("Botão de Foto clicado!")
                photo_app_state = "ARMING"
                photo_timer_start_time = time.time()
        
        # Proteção para não desenhar sobre a UI
        is_on_ui = (
            is_cursor_in_rect(cursor_pos, BTN_VOLTAR) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_RED) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_GREEN) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_BLUE) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_YELLOW) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_BLACK) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_ERASER) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_CLEAR) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_PHOTO)
        )
        
        can_draw = is_pinching and not is_on_ui and photo_app_state == "IDLE"

        if can_draw:
            if last_draw_point is None:
                last_draw_point = cursor_pos
            cv2.line(canvas, last_draw_point, cursor_pos, current_color, current_thickness)
            last_draw_point = cursor_pos
        else:
            last_draw_point = None
        
        if overlay_text:
            cv2.putText(img_display, overlay_text, (50+2, 70+2), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,0), 6)
            cv2.putText(img_display, overlay_text, (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255,255,255), 2)
        if countdown_text:
            font_scale = 5.0; thickness = 15
            text_size = cv2.getTextSize(countdown_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]
            text_x = (WIDTH - text_size[0]) // 2 
            text_y = (HEIGHT + text_size[1]) // 2     
            cv2.putText(img_display, countdown_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0,0,0), thickness + 10)
            cv2.putText(img_display, countdown_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0,0,255), thickness)
        
        img = img_display
        
    
    # --- TELA DA CÂMERA (FOTO) ---
    elif current_screen == "FOTO":
        overlay_text = ""
        countdown_text = ""
        
        # --- MUDANÇA: Lógica de "Armar" (3s segurando) e "Pose" (3s) (CORRIGIDO) ---
        is_hand_open = (dedos_nav == [1, 1, 1, 1, 1])
        
        if photo_app_state == "IDLE":
            overlay_text = "Segure a mao aberta por 3s"
            
            if is_hand_open:
                # Se a mão está aberta, inicia o timer (se não tiver começado)
                if photo_timer_start_time == 0:
                    photo_timer_start_time = time.time()
                
                time_held = time.time() - photo_timer_start_time
                # Usa o TIMER_ARM_HOLD (que é 3)
                countdown_value = TIMER_ARM_HOLD - int(time_held) 
                
                # Evita que o countdown mostre "0" antes de pular
                if countdown_value <= 0: countdown_value = 1 
                countdown_text = str(countdown_value)
                
                # Se segurou pelos 3 segundos
                if time_held >= TIMER_ARM_HOLD:
                    photo_app_state = "POSING"
                    photo_timer_start_time = time.time() # Reseta o timer para a pose
                    print("Armado! Faca a pose...")
                    
            else:
                # Se a mão não estiver aberta, reseta o timer
                photo_timer_start_time = 0
                countdown_text = "" # Limpa a contagem se a mão for solta
        
        # ESTADO 2: Contando 3s para a "Pose"
        # Este bloco agora roda mesmo se a mão desaparecer
        elif photo_app_state == "POSING": 
            time_elapsed = time.time() - photo_timer_start_time
            countdown_value = TIMER_POSING - int(time_elapsed)
            
            if countdown_value > 0:
                countdown_text = str(countdown_value)
                overlay_text = "Faca a pose!"
            else:
                # --- MUDANÇA V2: Salvar foto "Normal" ---
                filename_base = f"foto_normal_{int(time.time())}.jpg"
                img_clean_flipped = cv2.flip(img_raw, 1) 
                
                # --- MUDANÇA: Aplicar Moldura ---
                imagem_final = img_clean_flipped.copy() # Pega a imagem limpa
                if frame_ok:
                    draw_sprite(imagem_final, sprite_moldura, 0, 0)
                # --- Fim da mudança ---

                local_path = os.path.join(output_folder, filename_base)
                cv2.imwrite(local_path, imagem_final) # Salva a imagem com moldura
                print(f"Foto salva em: {local_path}")
                    
                # Envia para o Banco de Dados (com score 0)
                insert_score_to_db(0, filename_base)
                # --- Fim da Mudança V2 ---
                
                photo_app_state = "CAPTURED"
                photo_flash_start_time = time.time()
        
        # ESTADO 3: A foto foi tirada, mostrar feedback
        if photo_app_state == "CAPTURED":
        # --- Fim da mudança ---
            
            overlay_text = "FOTO CAPTURADA!"
            if time.time() - photo_flash_start_time < 0.5:
                cv2.rectangle(img, (0, 0), (WIDTH, HEIGHT), (255, 255, 255), -1)
            else:
                current_screen = "MENU"
                photo_app_state = "IDLE" 
                
        # Desenhar textos da Câmera
        if overlay_text:
            cv2.putText(img, overlay_text, (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,0), 6)
            cv2.putText(img, overlay_text, (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255,255,255), 2)
        if countdown_text:
            font_scale = 5.0; thickness = 15
            text_size = cv2.getTextSize(countdown_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]
            text_x = WIDTH - text_size[0] - 50 
            text_y = text_size[1] + 50         
            cv2.putText(img, countdown_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0,0,0), thickness + 10)
            cv2.putText(img, countdown_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0,0,255), thickness)
        
        draw_button(img, BTN_VOLTAR, "Voltar")
        if click_detected and is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
            current_screen = "MENU"
            photo_app_state = "IDLE" 
            
    # --- TELA DO JOGO ---
    elif current_screen == "JOGO" and pygame_ok:
        
        # Fundo azul 50/50
        light_blue_bg = np.full_like(img, (255, 230, 200)) # BGR: Azul claro
        img = cv2.addWeighted(img, 0.5, light_blue_bg, 0.5, 0)
        
        # Lógica do Jogo
        if game_state == "START":
            cv2.putText(img, "FLAPPY DEDO", (WIDTH // 2 - 270, HEIGHT // 2 - 150), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 255, 255), 8)
            cv2.putText(img, "Controle o 'passaro' com o indicador", (WIDTH // 2 - 400, HEIGHT // 2 + 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)
            
            if click_detected: # Começa com clique
                game_state = "PLAYING"
                game_start_time = time.time()
                game_score = 0
                game_pipes = []
                game_bird_y = HEIGHT // 2

        elif game_state == "PLAYING":
            
            # Dificuldade Progressiva
            difficulty_level = game_score // 5
            current_pipe_speed = min(30, game_pipe_speed + difficulty_level * 2) 
            current_pipe_gap = max(120, game_pipe_gap - difficulty_level * 10) 
            
            # Controle: Seguir o Dedo
            if results.multi_hand_landmarks:
                game_bird_y = cursor_pos[1]
            
            # Lógica dos Canos
            current_time = time.time()
            if current_time - game_last_pipe_time > game_pipe_interval:
                h = random.randint(150, HEIGHT - 150 - current_pipe_gap)
                game_pipes.append({"x": WIDTH, "height": h})
                game_last_pipe_time = current_time

            new_pipes = []
            for pipe in game_pipes:
                pipe["x"] -= current_pipe_speed
                x, h = pipe["x"], pipe["height"]
                
                # Desenho de Canos (Sprite ou fallback)
                if sprites_ok:
                    pipe_cima_y = h - PIPE_HEIGHT 
                    draw_sprite(img, sprite_cano_cima, x, pipe_cima_y)
                    pipe_baixo_y = h + current_pipe_gap
                    draw_sprite(img, sprite_cano_baixo, x, pipe_baixo_y)
                else:
                    cv2.rectangle(img, (x, 0), (x + game_pipe_width, h), (0, 200, 0), -1)
                    cv2.rectangle(img, (x, h + current_pipe_gap), (x + game_pipe_width, HEIGHT), (0, 200, 0), -1)

                # Lógica de Colisão (Sprite)
                bird_rect = (BIRD_X_POS, game_bird_y - BIRD_HEIGHT // 2, 
                             BIRD_X_POS + BIRD_WIDTH, game_bird_y + BIRD_HEIGHT // 2)
                pipe_cima_rect = (x, 0, x + game_pipe_width, h)
                pipe_baixo_rect = (x, h + current_pipe_gap, x + game_pipe_width, HEIGHT)

                if (check_collision(bird_rect, pipe_cima_rect) or check_collision(bird_rect, pipe_baixo_rect)) and \
                   game_state != "GAME_OVER":
                    
                    # --- MUDANÇA V2: Salvar Score e Imagem ---
                    filename_base = f"foto_gameover_score_{game_score}_{int(time.time())}.jpg"
                    img_clean_flipped = cv2.flip(img_raw, 1) # Salva a imagem limpa
                    
                    # --- MUDANÇA: Aplicar Moldura ---
                    imagem_final = img_clean_flipped.copy() # Pega a imagem limpa
                    if frame_ok:
                        draw_sprite(imagem_final, sprite_moldura, 0, 0)
                    # --- Fim da mudança ---

                    local_path = os.path.join(output_folder, filename_base)
                    cv2.imwrite(local_path, imagem_final) # Salva a imagem com moldura
                    print(f"Foto Game Over salva em: {local_path}")
                        
                    # Envia para o Banco de Dados
                    insert_score_to_db(game_score, filename_base)
                    # --- Fim da Mudança V2 ---

                    game_state = "GAME_OVER"
                    if pygame_ok: pygame.mixer.music.stop()

                # Pontuação
                if x + game_pipe_width < BIRD_X_POS and "counted" not in pipe:
                    game_score += 1
                    pipe["counted"] = True
                    if ponto_sound:
                        ponto_sound.play()

                if x + game_pipe_width > 0:
                    new_pipes.append(pipe)
            game_pipes = new_pipes

            # Checa colisão com teto/chão
            if (game_bird_y - BIRD_HEIGHT // 2 <= 0 or game_bird_y + BIRD_HEIGHT // 2 >= HEIGHT) and game_state != "GAME_OVER":
                
                # --- MUDANÇA V2: Salvar Score e Imagem ---
                filename_base = f"foto_gameover_score_{game_score}_{int(time.time())}.jpg"
                img_clean_flipped = cv2.flip(img_raw, 1) # Salva a imagem limpa
                
                # --- MUDANÇA: Aplicar Moldura ---
                imagem_final = img_clean_flipped.copy() # Pega a imagem limpa
                if frame_ok:
                    draw_sprite(imagem_final, sprite_moldura, 0, 0)
                # --- Fim da mudança ---
                
                local_path = os.path.join(output_folder, filename_base)
                cv2.imwrite(local_path, imagem_final) # Salva a imagem com moldura
                print(f"Foto Game Over salva em: {local_path}")
                
                insert_score_to_db(game_score, filename_base)
                # --- Fim da Mudança V2 ---

                game_state = "GAME_OVER"
                if pygame_ok: pygame.mixer.music.stop()
            
            # Desenhar Pássaro (Sprite)
            if sprites_ok:
                bird_draw_y = game_bird_y - BIRD_HEIGHT // 2
                draw_sprite(img, sprite_passaro, BIRD_X_POS, bird_draw_y)
            else:
                cv2.circle(img, (BIRD_X_POS + BIRD_WIDTH // 2, game_bird_y), BIRD_WIDTH // 2, (0, 255, 255), -1)
            
            # Pontos
            cv2.putText(img, f"Pontos: {game_score}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0,0,0), 8)
            cv2.putText(img, f"Pontos: {game_score}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)

        elif game_state == "GAME_OVER":
            cv2.putText(img, "GAME OVER", (WIDTH // 2 - 280, HEIGHT // 2 - 150), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 255), 10)
            cv2.putText(img, f"Pontos: {game_score}", (WIDTH // 2 - 120, HEIGHT // 2 + 50), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)
            
            draw_button(img, BTN_GAME_RESTART, "REINICIAR", bg_color=(0, 200, 0))
            
            if click_detected:
                if is_cursor_in_rect(cursor_pos, BTN_GAME_RESTART):
                    game_state = "PLAYING"
                    game_start_time = time.time()
                    game_score = 0
                    game_pipes = []
                    game_bird_y = HEIGHT // 2
                    if pygame_ok: pygame.mixer.music.play(-1) 
            
        # Botão Voltar (sempre visível no jogo, incluindo Game Over)
        draw_button(img, BTN_VOLTAR, "Sair")
        
        # Checa clique no "Sair"
        if click_detected and is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
            current_screen = "MENU"
            if pygame_ok: pygame.mixer.music.stop() 

    # ------------------- Desenhar cursor (sempre por cima) -------------------
    if results.multi_hand_landmarks:
        if not (current_screen == "DESENHO" and photo_app_state != "IDLE"):
            cursor_int = cursor_pos
            cursor_color = (0, 255, 0) if not is_pinching else (0, 0, 255)
            cv2.circle(img, cursor_int, 15, cursor_color, -1)
            cv2.circle(img, cursor_int, 15, (255, 255, 255), 3)


    # Mostrar Imagem Final
    cv2.imshow("Gesture Suite v1.0", img)
    
    # --- Controle de FPS ---
    elapsed_total = time.time() - start_time_frame
    sleep_time = tempo_por_frame - elapsed_total
    if sleep_time > 0:
        time.sleep(sleep_time * 0.95) 

    key = cv2.waitKey(1)
    if key == 27 or key == ord('q'): # Pressione ESC ou 'q' para sair
        break

# limpeza
cap.release()
cv2.destroyAllWindows()
if pygame_ok:
    pygame.mixer.quit()