import cv2
import mediapipe as mp
import math
import time
from collections import Counter, deque
import numpy as np
import os
import random

# --- Tenta importar e inicializar o Pygame (para o jogo) ---
try:
    import pygame
    pygame.mixer.init()
    # Tenta carregar os sons
    try:
        pygame.mixer.music.load("musica2.mp3") # Fundo do Jogo
        pygame.mixer.music.set_volume(0.3)
        ponto_sound = pygame.mixer.Sound("ponto.mp3") # Som de ponto
        ponto_sound.set_volume(0.3)
        pygame_ok = True
    except Exception as e:
        print(f"Aviso: Nao foi possivel carregar arquivos de som (musica2.mp3, ponto.mp3): {e}")
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
# max_num_hands=2 para suportar 2 mãos
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=2,
                       min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

# Estilo de desenho dos landmarks
estilo_ponto = mp_draw.DrawingSpec(color=(0, 200, 0), thickness=1, circle_radius=2)
estilo_linha = mp_draw.DrawingSpec(color=(20, 120, 255), thickness=2)

# Captura (resolução 1280x720)
cap = cv2.VideoCapture(0)
WIDTH, HEIGHT = 1280, 720
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
cap.set(cv2.CAP_PROP_FPS, 30)
fps_target = 30
tempo_por_frame = 1.0 / fps_target

# Criar a pasta "fotos" se ela não existir
output_folder = "fotos"
os.makedirs(output_folder, exist_ok=True)

# ------------------- MUDANÇA: Carregar Sprites (Imagens) -------------------
try:
    # Carrega as imagens (-1 = carregar com canal alfa/transparência)
    sprite_passaro = cv2.imread("passaro.png", -1)
    sprite_cano_cima = cv2.imread("pipe_cima.png", -1)
    sprite_cano_baixo = cv2.imread("pipe_baixo.png", -1)

    if sprite_passaro is None or sprite_cano_cima is None or sprite_cano_baixo is None:
        raise IOError("Nao foi possivel carregar um ou mais arquivos de sprite (passaro.png, pipe_cima.png, pipe_baixo.png)")
    
    # --- Define o tamanho dos sprites ---
    # Pássaro (vamos definir um tamanho fixo)
    BIRD_WIDTH, BIRD_HEIGHT = 85, 60 # (Largura, Altura) - Ajuste se necessário
    sprite_passaro = cv2.resize(sprite_passaro, (BIRD_WIDTH, BIRD_HEIGHT))
    
    # --- MUDANÇA: Forçar o redimensionamento dos canos ---
    # O usuário reportou que os canos estão muito grandes (ex: 508x608)
    # Vamos definir um tamanho fixo para eles.
    PIPE_TARGET_WIDTH = 150  # Largura do cano (em pixels)
    PIPE_TARGET_HEIGHT = 600 # Altura do cano (para cobrir a tela)

    # Redimensiona os sprites dos canos para o tamanho-alvo
    sprite_cano_cima = cv2.resize(sprite_cano_cima, (PIPE_TARGET_WIDTH, PIPE_TARGET_HEIGHT))
    sprite_cano_baixo = cv2.resize(sprite_cano_baixo, (PIPE_TARGET_WIDTH, PIPE_TARGET_HEIGHT))

    # Atualiza as variáveis globais com o novo tamanho
    PIPE_WIDTH, PIPE_HEIGHT = PIPE_TARGET_WIDTH, PIPE_TARGET_HEIGHT
    # --- Fim da mudança ---

    sprites_ok = True
    print("Sprites do jogo (passaro, canos) carregados com sucesso!")

except Exception as e:
    print(f"----------------------------------------------------")
    print(f"AVISO: Nao foi possivel carregar os sprites: {e}")
    print(f"O jogo vai rodar no 'modo classico' (com circulos e retangulos).")
    print(f"Verifique se os arquivos 'passaro.png', 'pipe_cima.png' e 'pipe_baixo.png' estao na pasta.")
    print(f"----------------------------------------------------")
    sprites_ok = False
    # Define tamanhos padrão para o modo clássico
    BIRD_WIDTH, BIRD_HEIGHT = 50, 50 # (Raio de 25)
    PIPE_WIDTH = 120 # (Valor antigo)
# --- Fim da mudança ---


# ------------------- Estado da aplicação -------------------
current_screen = "MENU"  # MENU, GESTOS, DESENHO, FOTO, JOGO
# Cursor (usa média exponencial para suavização)
cursor_pos = (WIDTH // 2, HEIGHT // 2)
last_cursor_pos = (WIDTH // 2, HEIGHT // 2) # Para suavização
EMA_ALPHA = 0.3 # 0.1 = muito suave, 0.9 = muito rápido

# Clique por pinça (mão de navegação)
click_frames = 0
CLICK_THRESHOLD = 3 # Frames segurando pinça para "clicar"
CLICK_DISTANCE = 50 # Distância (pixels) para considerar pinça

# Gestos (para tela GESTOS)
BUFFER_SIZE = 5
gesture_buffer = deque(maxlen=BUFFER_SIZE)
stable_gesture_text = ""

# Desenho (para tela DESENHO)
canvas = np.ones((HEIGHT, WIDTH, 3), dtype=np.uint8) * 255 # Começa BRANCO
last_draw_point = None # Para desenhar linhas contínuas
current_color = (0, 0, 0)  # Pincel padrão agora é PRETO
current_thickness = 12 # Pincel normal

# Câmera (para tela FOTO e agora DESENHO)
photo_app_state = "IDLE" # IDLE, ARMING, POSING, CAPTURED
photo_timer_start_time = 0
photo_flash_start_time = 0
TIMER_PHOTO_HOLD = 3 # 3 segundos segurando a mão

# Jogo (para tela JOGO)
game_state = "START"
game_bird_y = HEIGHT // 2
BIRD_X_POS = (WIDTH // 2) - 150 # Posição X fixa (mais à esquerda)
game_pipes = []
game_pipe_speed = 20     # Velocidade base dos canos
game_pipe_gap = 220      # Vão base entre os canos
game_pipe_width = PIPE_WIDTH # Usa a largura do sprite (ou o padrão)
game_last_pipe_time = 0
game_pipe_interval = 1.3 # Tempo entre os canos
game_score = 0
game_start_time = 0

# ------------------- Funções de Detecção -------------------
def distancia(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def detectar_dedos_vetorial(lm_list):
    """
    Retorna lista de 5 ints (0/1) para [polegar, indicador, medio, anelar, minimo]
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
        return angle < math.radians(30)  # 30 graus

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
# Botões do Menu (Layout 2x2)
BTN_MENU_GESTOS = (100, 150, 550, 300)
BTN_MENU_DESENHO = (730, 150, 1180, 300)
BTN_MENU_FOTO = (100, 400, 550, 550)
BTN_MENU_JOGO = (730, 400, 1180, 550)
BTN_VOLTAR = (1030, 620, 1260, 700) # Botão de Voltar Padrão
BTN_GAME_RESTART = (WIDTH // 2 - 200, HEIGHT // 2 + 100, WIDTH // 2 + 200, HEIGHT // 2 + 200)

# Paleta de Desenho (Vertical na Direita)
# Cores (BGR)
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
    
    # Adiciona borda normal e borda de seleção
    border_color = (0, 255, 255) if is_selected else (255, 255, 255)
    border_thickness = 4 if is_selected else 3
    cv2.rectangle(img, (x1, y1), (x2, y2), border_color, border_thickness) # Borda
    
    # Centraliza texto
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 1.3
    thickness = 3
    # Ajusta o scale se o texto for muito grande para o botão (ex: Limpar, Reiniciar)
    text_size = cv2.getTextSize(text, font, scale, thickness)[0]
    if text_size[0] > (x2 - x1 - 20): # Se for maior que a largura do botão
        scale = 1.0 # Diminui a fonte
        text_size = cv2.getTextSize(text, font, scale, thickness)[0]
        
    tx = x1 + (x2 - x1 - text_size[0]) // 2
    ty = y1 + (y2 - y1 + text_size[1]) // 2
    cv2.putText(img, text, (tx, ty), font, scale, (255, 255, 255), thickness)

def is_cursor_in_rect(cursor_xy, rect):
    x, y = cursor_xy
    x1, y1, x2, y2 = rect
    return x1 < x < x2 and y1 < y < y2

# ------------------- MUDANÇA: Novas Funções de Sprite -------------------
def draw_sprite(background, sprite, x, y):
    """
    Desenha um sprite (imagem PNG com alfa) sobre o background.
    x, y é a posição do canto SUPERIOR ESQUERDO do sprite.
    """
    try:
        h, w, channels = sprite.shape
    except ValueError:
        print("Erro: Sprite com formato inválido. Precisa de 4 canais (RGBA).")
        return
        
    x, y = int(x), int(y) # Posição (canto superior esquerdo)

    # Se o sprite não tem canal Alfa, apenas desenha
    if channels < 4:
        # TODO: Implementar desenho sem alfa se necessário
        # Por agora, vamos focar no PNG com alfa
        print("Aviso: Sprite nao tem canal alfa (transparencia).")
        return

    # Extrair o canal alfa (transparência)
    alpha = sprite[:, :, 3] / 255.0 # (0.0 a 1.0)
    alpha_inv = 1.0 - alpha

    # Limites para não desenhar fora da tela (evita crash)
    y1, y2 = max(0, y), min(HEIGHT, y + h)
    x1, x2 = max(0, x), min(WIDTH, x + w)
    
    # Limites do sprite (caso ele esteja cortado na borda)
    sprite_y1, sprite_y2 = max(0, -y), min(h, HEIGHT - y)
    sprite_x1, sprite_x2 = max(0, -x), min(w, WIDTH - x)

    # Se o sprite estiver 100% fora da tela
    if y1 >= y2 or x1 >= x2 or sprite_y1 >= sprite_y2 or sprite_x1 >= sprite_x2:
        return

    # Pegar a ROI (Region of Interest) do background
    roi = background[y1:y2, x1:x2]
    # Pegar o sprite cortado (e seu alfa)
    sprite_cut = sprite[sprite_y1:sprite_y2, sprite_x1:sprite_x2]
    alpha_cut = alpha[sprite_y1:sprite_y2, sprite_x1:sprite_x2]
    
    # Redimensiona o alfa para 3D (para multiplicar pelos 3 canais BGR)
    alpha_3d = cv2.merge([alpha_cut, alpha_cut, alpha_cut])
    alpha_inv_3d = cv2.merge([1.0-alpha_cut, 1.0-alpha_cut, 1.0-alpha_cut])

    # Combinar as imagens (frente * alfa) + (fundo * 1-alfa)
    roi_bg = cv2.multiply(alpha_inv_3d, roi.astype(float))
    sprite_fg = cv2.multiply(alpha_3d, sprite_cut[:,:,:3].astype(float))
    
    # Junta as duas partes e coloca de volta no background
    background[y1:y2, x1:x2] = cv2.add(roi_bg, sprite_fg).astype(np.uint8)

def check_collision(bird_rect, pipe_rect):
    """Verifica colisão de Bounding Box (AABB)"""
    bx1, by1, bx2, by2 = bird_rect
    px1, py1, px2, py2 = pipe_rect
    
    # Se não houver sobreposição em X
    if bx1 > px2 or bx2 < px1:
        return False
    # Se não houver sobreposição em Y
    if by1 > py2 or by2 < py1:
        return False
    # Se chegou aqui, houve colisão
    return True
# --- Fim da mudança ---

# ------------------- Loop principal -------------------
while True:
    start_time_frame = time.time()
    
    # --- 'img_raw' é a imagem limpa, para salvar a foto ---
    success, img_raw = cap.read()
    if not success:
        print("Erro ao abrir câmera.")
        break

    # 'img' é a imagem do display (espelhada)
    img = cv2.flip(img_raw, 1)
    
    # Processamento do MediaPipe
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)

    # Resetar variáveis por frame
    click_detected = False
    pinch_dist = 999
    is_pinching = False
    lm_list_nav = None # Landmarks da mão de navegação
    dedos_nav = [0,0,0,0,0]
    nav_hand_index = -1 # Reseta o índice da mão de navegação
    
    # --- Lógica de Detecção de Mão (Mão de Navegação) ---
    if results.multi_hand_landmarks and results.multi_handedness:
        # Tenta encontrar a mão direita para navegação
        for i, hand_info in enumerate(results.multi_handedness):
            if hand_info.classification[0].label == "Right":
                nav_hand_index = i
                break
        
        # Se não achar a direita, usa a primeira mão que aparecer
        if nav_hand_index == -1:
            nav_hand_index = 0
            
        handLms_nav = results.multi_hand_landmarks[nav_hand_index]
        
        # Desenha a mão de navegação (apenas se não estiver tirando foto no modo Desenho)
        if not (current_screen == "DESENHO" and photo_app_state != "IDLE"):
             # --- MUDANÇA: Desenhando a mão no Jogo novamente ---
             mp_draw.draw_landmarks(img, handLms_nav, mp_hands.HAND_CONNECTIONS, estilo_ponto, estilo_linha)
             # --- Fim da mudança ---

        # Extrai landmarks da mão de navegação
        lm_list_nav = []
        for lm in handLms_nav.landmark:
            lm_list_nav.append((int(lm.x * WIDTH), int(lm.y * HEIGHT)))
        
        # Atualiza Posição do Cursor (Suavizada)
        raw_cursor_pos = lm_list_nav[8] # Ponta do indicador
        cursor_pos = (int(EMA_ALPHA * raw_cursor_pos[0] + (1 - EMA_ALPHA) * last_cursor_pos[0]),
                      int(EMA_ALPHA * raw_cursor_pos[1] + (1 - EMA_ALPHA) * last_cursor_pos[1]))
        last_cursor_pos = cursor_pos
        
        # Detecta dedos da mão de navegação
        dedos_nav = detectar_dedos_vetorial(lm_list_nav)
        
        # Lógica de Clique (Pinça) - (Não clica se estiver em contagem)
        if photo_app_state == "IDLE": # Só permite clicar se não estiver em contagem
            pinch_dist = distancia(lm_list_nav[4], lm_list_nav[8]) # Polegar + Indicador
            is_pinching = (pinch_dist < CLICK_DISTANCE)
            
            if is_pinching:
                click_frames += 1
            else:
                click_frames = 0 # Reseta se a pinça soltar
                
            if click_frames == CLICK_THRESHOLD: # Exatamente no frame N
                click_detected = True # Dispara um "clique" de 1 frame
                print("CLICK DETECTED")

    else:
        # Se não houver mão, reseta o clique
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
        
        # --- MUDANÇA: Verifica se pygame E sprites estão ok ---
        if pygame_ok and sprites_ok:
            draw_button(img, BTN_MENU_JOGO, "Jogo")
        else:
            draw_button(img, BTN_MENU_JOGO, "Jogo (OFF)", bg_color=(100,100,100)) # Botão desabilitado

        # Checa cliques nos botões
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
            
            elif is_cursor_in_rect(cursor_pos, BTN_MENU_JOGO) and pygame_ok and sprites_ok: # <-- MUDANÇA
                current_screen = "JOGO"
                # Reseta o Jogo
                game_state = "START"
                game_bird_y = HEIGHT // 2
                game_pipes = []
                game_score = 0
                game_start_time = time.time()
                if pygame_ok and pygame.mixer.music.get_busy() == False:
                    pygame.mixer.music.play(-1) # Toca a música do jogo em loop
            # --- Fim da mudança ---

    # --- TELA DE GESTOS ---
    elif current_screen == "GESTOS":
        draw_button(img, BTN_VOLTAR, "Voltar")

        # Conta os dedos de TODAS as mãos na tela
        total_fingers = 0
        if results.multi_hand_landmarks:
            for i, handLms in enumerate(results.multi_hand_landmarks):
                lm_list = []
                for lm in handLms.landmark:
                    lm_list.append((int(lm.x * WIDTH), int(lm.y * HEIGHT)))
                
                dedos = detectar_dedos_vetorial(lm_list)
                total_fingers += sum(dedos)
                
                # Desenha os landmarks da segunda mão (se houver e não for a mão de nav)
                if i != nav_hand_index:
                     mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS, estilo_ponto, estilo_linha)

        # Lógica de texto (baseado apenas na mão de navegação)
        if dedos_nav == [0, 0, 0, 0, 0]: current_gesture_text = "Punho Fechado"
        elif dedos_nav == [0, 1, 0, 0, 0]: current_gesture_text = "Apontando (1)"
        elif dedos_nav == [0, 1, 1, 0, 0]: current_gesture_text = "Paz (2)"
        elif dedos_nav == [1, 0, 0, 0, 0]: current_gesture_text = "Joia"
        elif dedos_nav == [1, 1, 1, 1, 1]: current_gesture_text = "Mao Aberta (5)"
        else: current_gesture_text = ""
        
        # Filtro de estabilização
        gesture_buffer.append(current_gesture_text)
        if len(gesture_buffer) == BUFFER_SIZE:
            count_data = Counter(gesture_buffer)
            if count_data: # Proteção contra buffer vazio
                most_common = count_data.most_common(1)[0]
                if most_common[1] > BUFFER_SIZE // 2: # Se for maioria
                    stable_gesture_text = most_common[0]

        if stable_gesture_text:
            cv2.putText(img, stable_gesture_text, (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0,0,0), 8)
            cv2.putText(img, stable_gesture_text, (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (255, 255, 255), 3)

        # Mostra o TOTAL de dedos (2 mãos)
        cv2.putText(img, f"Total de Dedos: {total_fingers}", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0,0,0), 8)
        cv2.putText(img, f"Total de Dedos: {total_fingers}", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 3)

        if click_detected and is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
            current_screen = "MENU"
            gesture_buffer.clear()
            stable_gesture_text = ""

    # --- TELA DE DESENHO ---
    elif current_screen == "DESENHO":
        
        # Lógica de Timer da Câmera (copiada da tela FOTO)
        overlay_text = ""
        countdown_text = ""
        
        # Lógica de máscara para canvas BRANCO
        img_gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
        # THRESH_BINARY_INV: Desenho (0-254) vira 255 (branco), Fundo (255) vira 0 (preto)
        _, mask = cv2.threshold(img_gray, 254, 255, cv2.THRESH_BINARY_INV) 

        img_bg = cv2.bitwise_and(img, img, mask=cv2.bitwise_not(mask))
        img_fg = cv2.bitwise_and(canvas, canvas, mask=mask)
        img_with_drawing = cv2.add(img_bg, img_fg)
        
        # A imagem que vamos mostrar (com UI por cima)
        img_display = img_with_drawing.copy()

        # Lógica de estado da Câmera
        if photo_app_state == "ARMING": 
            time_elapsed = time.time() - photo_timer_start_time
            countdown_value = TIMER_ARMING - int(time_elapsed)
            
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
                # Tirar a foto
                filename = os.path.join(output_folder, f"foto_desenho_{int(time.time())}.jpg")
                # Salva a imagem COM O DESENHO
                cv2.imwrite(filename, img_with_drawing) 
                print(f"Foto salva: {filename}")
                
                photo_app_state = "CAPTURED"
                photo_flash_start_time = time.time()
        
        # Estado de feedback (flash)
        if photo_app_state == "CAPTURED":
            overlay_text = "FOTO CAPTURADA!"
            if time.time() - photo_flash_start_time < 0.5:
                # Aplica o flash na img_display
                cv2.rectangle(img_display, (0, 0), (WIDTH, HEIGHT), (255, 255, 255), -1)
            else:
                photo_app_state = "IDLE" # Reseta
                
        # Desenha a nova paleta de cores (na img_display)
        draw_button(img_display, BTN_DRAW_RED, "Vermelho", bg_color=(0,0,255), is_selected=(current_color == (0,0,255)))
        draw_button(img_display, BTN_DRAW_GREEN, "Verde", bg_color=(0,255,0), is_selected=(current_color == (0,255,0)))
        draw_button(img_display, BTN_DRAW_BLUE, "Azul", bg_color=(255,0,0), is_selected=(current_color == (255,0,0)))
        draw_button(img_display, BTN_DRAW_YELLOW, "Amarelo", bg_color=(0,255,255), is_selected=(current_color == (0,255,255)))
        
        # Botão "Preto" (selecionado se for preto e fino)
        draw_button(img_display, BTN_DRAW_BLACK, "Preto", bg_color=(50,50,50), is_selected=(current_color == (0,0,0) and current_thickness == 12))
        
        # Botão "Borracha" (selecionado se for branco e grosso)
        draw_button(img_display, BTN_DRAW_ERASER, "Borracha", bg_color=(200,200,200), is_selected=(current_color == (255,255,255)))
        
        draw_button(img_display, BTN_DRAW_CLEAR, "Limpar")
        draw_button(img_display, BTN_DRAW_PHOTO, "Foto") # Novo botão de foto
        draw_button(img_display, BTN_VOLTAR, "Voltar")
        
        # Lógica de clique (só funciona se não estiver tirando foto)
        if click_detected and photo_app_state == "IDLE":
            if is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
                current_screen = "MENU"
            
            # Botões de Cor
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
            
            # Clique no "Preto"
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_BLACK):
                current_color = (0, 0, 0) # PRETO
                current_thickness = 12
                
            # Botão Borracha (agora é BRANCO)
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_ERASER):
                current_color = (255, 255, 255) # Cor do canvas (BRANCO)
                current_thickness = 40 # Borracha mais grossa
            
            # Botão Limpar Tela
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_CLEAR):
                canvas.fill(255) # Preenche o canvas com BRANCO
            
            # Botão de Foto
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
        
        # Gesto de desenhar: Pinca (polegar + indicador)
        # Não desenha se a pinça estiver em cima de um botão ou se estiver tirando foto
        can_draw = is_pinching and not is_on_ui and photo_app_state == "IDLE"

        if can_draw:
            if last_draw_point is None:
                last_draw_point = cursor_pos
            cv2.line(canvas, last_draw_point, cursor_pos, current_color, current_thickness)
            last_draw_point = cursor_pos
        else:
            last_draw_point = None
        
        # Desenha os textos da Câmera (se houver) sobre a 'img_display'
        if overlay_text:
            # Sombra
            cv2.putText(img_display, overlay_text, (50+2, 70+2), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,0), 6)
            # Texto
            cv2.putText(img_display, overlay_text, (50, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255,255,255), 2)
        if countdown_text:
            font_scale = 5.0; thickness = 15
            text_size = cv2.getTextSize(countdown_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0]
            text_x = (WIDTH - text_size[0]) // 2 # Centralizado
            text_y = (HEIGHT + text_size[1]) // 2     
            cv2.putText(img_display, countdown_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0,0,0), thickness + 10)
            cv2.putText(img_display, countdown_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0,0,255), thickness)
        
        # (Troca 'img' por 'img_display' no imshow)
        img = img_display
        
    
    # --- TELA DA CÂMERA (FOTO) ---
    elif current_screen == "FOTO":
        overlay_text = ""
        countdown_text = ""
        
        # --- MUDANÇA: Lógica de "Segurar Mão Aberta" por 3s (Corrigida) ---
        is_hand_open = (dedos_nav == [1, 1, 1, 1, 1])
        
        if photo_app_state == "IDLE":
            overlay_text = "Segure a mao aberta por 3s"
            
            if is_hand_open:
                # Se a mão está aberta, inicia o timer (se não tiver começado)
                if photo_timer_start_time == 0:
                    photo_timer_start_time = time.time()
                
                time_held = time.time() - photo_timer_start_time
                countdown_value = TIMER_PHOTO_HOLD - int(time_held)
                countdown_text = str(countdown_value)
                
                # Se segurou pelos 3 segundos
                if time_held >= TIMER_PHOTO_HOLD:
                    # Tirar a foto
                    filename = os.path.join(output_folder, f"foto_normal_{int(time.time())}.jpg")
                    img_clean_flipped = cv2.flip(img_raw, 1) # Salva a imagem limpa e flipada
                    cv2.imwrite(filename, img_clean_flipped) 
                    print(f"Foto salva: {filename}")
                    
                    photo_app_state = "CAPTURED"
                    photo_flash_start_time = time.time()
                    photo_timer_start_time = 0 # Reseta o timer
                    
            else:
                # Se a mão não estiver aberta, reseta o timer
                photo_timer_start_time = 0
                countdown_text = "" # Limpa a contagem se a mão for solta
                
        # Estado de feedback (flash)
        if photo_app_state == "CAPTURED":
        # --- Fim da mudança ---
            
            overlay_text = "FOTO CAPTURADA!"
            if time.time() - photo_flash_start_time < 0.5:
                cv2.rectangle(img, (0, 0), (WIDTH, HEIGHT), (255, 255, 255), -1)
            else:
                # Volta ao Menu automaticamente
                current_screen = "MENU"
                photo_app_state = "IDLE" # <-- CORREÇÃO DO BUG DA PINÇA
                
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
        
        # Botão Voltar (precisa ser checado *depois* da lógica do flash)
        draw_button(img, BTN_VOLTAR, "Voltar")
        if click_detected and is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
            current_screen = "MENU"
            photo_app_state = "IDLE" # Garante o reset
            
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
                
                # --- MUDANÇA: Desenho de Canos 3D (ou fallback) ---
                if sprites_ok:
                    # 1. Cano Cima
                    pipe_cima_y = h - PIPE_HEIGHT # Alinha a base do sprite com a altura h
                    draw_sprite(img, sprite_cano_cima, x, pipe_cima_y)
                    # 2. Cano Baixo
                    pipe_baixo_y = h + current_pipe_gap
                    draw_sprite(img, sprite_cano_baixo, x, pipe_baixo_y)
                else:
                    # Fallback para retângulos se os sprites falharam
                    cv2.rectangle(img, (x, 0), (x + game_pipe_width, h), (0, 200, 0), -1)
                    cv2.rectangle(img, (x, h + current_pipe_gap), (x + game_pipe_width, HEIGHT), (0, 200, 0), -1)
                # --- Fim da mudança ---

                # --- MUDANÇA: Lógica de Colisão (Sprite) ---
                # Bounding Box do Pássaro
                bird_rect = (BIRD_X_POS, game_bird_y - BIRD_HEIGHT // 2, 
                             BIRD_X_POS + BIRD_WIDTH, game_bird_y + BIRD_HEIGHT // 2)
                # Bounding Box dos Canos
                pipe_cima_rect = (x, 0, x + game_pipe_width, h)
                pipe_baixo_rect = (x, h + current_pipe_gap, x + game_pipe_width, HEIGHT)

                if (check_collision(bird_rect, pipe_cima_rect) or check_collision(bird_rect, pipe_baixo_rect)) and \
                   game_state != "GAME_OVER":
                # --- Fim da mudança ---
                    
                    # Tirar foto ao perder
                    filename = os.path.join(output_folder, f"foto_gameover_{int(time.time())}.jpg")
                    img_clean_flipped = cv2.flip(img_raw, 1) # Salva a imagem limpa
                    cv2.imwrite(filename, img_clean_flipped) 
                    print(f"Foto Game Over salva: {filename}")

                    game_state = "GAME_OVER"
                    if pygame_ok: pygame.mixer.music.stop()

                # Pontuação
                # --- MUDANÇA: Posição X do pássaro ---
                if x + game_pipe_width < BIRD_X_POS and "counted" not in pipe:
                # --- Fim da mudança ---
                    game_score += 1
                    pipe["counted"] = True
                    if ponto_sound:
                        ponto_sound.play()

                if x + game_pipe_width > 0:
                    new_pipes.append(pipe)
            game_pipes = new_pipes

            # Checa colisão com teto/chão
            if (game_bird_y - BIRD_HEIGHT // 2 <= 0 or game_bird_y + BIRD_HEIGHT // 2 >= HEIGHT) and game_state != "GAME_OVER":
                
                # Tirar foto ao perder
                filename = os.path.join(output_folder, f"foto_gameover_{int(time.time())}.jpg")
                img_clean_flipped = cv2.flip(img_raw, 1) # Salva a imagem limpa
                cv2.imwrite(filename, img_clean_flipped) 
                print(f"Foto Game Over salva: {filename}")

                game_state = "GAME_OVER"
                if pygame_ok: pygame.mixer.music.stop()
            
            # --- MUDANÇA: Desenhar Pássaro (Sprite) ---
            if sprites_ok:
                # Converte o centro (game_bird_y) para canto superior esquerdo
                bird_draw_y = game_bird_y - BIRD_HEIGHT // 2
                draw_sprite(img, sprite_passaro, BIRD_X_POS, bird_draw_y)
            else:
                # Fallback para círculo
                cv2.circle(img, (BIRD_X_POS + BIRD_WIDTH // 2, game_bird_y), BIRD_WIDTH // 2, (0, 255, 255), -1)
            # --- Fim da mudança ---
            
            # Pontos
            cv2.putText(img, f"Pontos: {game_score}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0,0,0), 8)
            cv2.putText(img, f"Pontos: {game_score}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)

        elif game_state == "GAME_OVER":
            cv2.putText(img, "GAME OVER", (WIDTH // 2 - 280, HEIGHT // 2 - 150), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 255), 10)
            cv2.putText(img, f"Pontos: {game_score}", (WIDTH // 2 - 120, HEIGHT // 2 + 50), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)
            
            # Lógica de botões
            draw_button(img, BTN_GAME_RESTART, "REINICIAR", bg_color=(0, 200, 0))
            
            if click_detected:
                if is_cursor_in_rect(cursor_pos, BTN_GAME_RESTART):
                    # Reinicia o jogo
                    game_state = "PLAYING"
                    game_start_time = time.time()
                    game_score = 0
                    game_pipes = []
                    game_bird_y = HEIGHT // 2
                    if pygame_ok: pygame.mixer.music.play(-1) # Reinicia a música
            
        # Botão Voltar (sempre visível no jogo, incluindo Game Over)
        draw_button(img, BTN_VOLTAR, "Sair")
        
        # Checa clique no "Sair"
        if click_detected and is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
            current_screen = "MENU"
            if pygame_ok: pygame.mixer.music.stop() # Para a música ao sair

    # ------------------- Desenhar cursor (sempre por cima) -------------------
    if results.multi_hand_landmarks:
        # Não desenha o cursor se estiver tirando foto no modo Desenho
       # --- MUDANÇA: Voltando a desenhar o cursor no Jogo ---
        if not (current_screen == "DESENHO" and photo_app_state != "IDLE"): # <-- Removido 'and current_screen != "JOGO"'
        # --- Fim da mudança ---
            cursor_int = cursor_pos
            # Cor verde, mas fica vermelha ao "clicar" (pinça)
            cursor_color = (0, 255, 0) if not is_pinching else (0, 0, 255)
            cv2.circle(img, cursor_int, 15, cursor_color, -1)
            cv2.circle(img, cursor_int, 15, (255, 255, 255), 3)


    # Mostrar Imagem Final
    cv2.imshow("Gesture Suite v1.0", img)
    
    # --- Controle de FPS ---
    elapsed_total = time.time() - start_time_frame
    sleep_time = tempo_por_frame - elapsed_total
    if sleep_time > 0:
        time.sleep(sleep_time * 0.95) # Pequena folga

    key = cv2.waitKey(1)
    if key == 27 or key == ord('q'): # Pressione ESC ou 'q' para sair
        break

# limpeza
cap.release()
cv2.destroyAllWindows()
if pygame_ok:
    pygame.mixer.quit()