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
canvas = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
last_draw_point = None # Para desenhar linhas contínuas
current_color = (255, 255, 255)  # branco
current_thickness = 12 # Pincel normal

# Câmera (para tela FOTO)
photo_app_state = "IDLE" # IDLE, ARMING, POSING, CAPTURED
photo_timer_start_time = 0
photo_flash_start_time = 0
TIMER_ARMING = 2
TIMER_POSING = 5

# Jogo (para tela JOGO)
game_state = "START"
game_bird_y = HEIGHT // 2
game_bird_radius = 25
game_gravity = 0.8       # Gravidade (puxa para baixo)
game_bird_vel = 0        # Velocidade vertical atual
game_lift = -15          # Força do "pulo" (para cima)
game_pipes = []
game_pipe_speed = 10     # Velocidade base dos canos
game_pipe_gap = 230      # Vão base entre os canos
game_pipe_width = 120
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

# Novos botões para a paleta de desenho
# Cores (BGR)
BTN_DRAW_RED = (50, 20, 100, 70)
BTN_DRAW_GREEN = (110, 20, 160, 70)
BTN_DRAW_BLUE = (170, 20, 220, 70)
BTN_DRAW_WHITE = (230, 20, 280, 70)
BTN_DRAW_ERASER = (300, 20, 350, 70) # Borracha (cor preta)
BTN_DRAW_CLEAR = (WIDTH - 220, 20, WIDTH - 50, 70) # Limpar tela


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
    # Ajusta o scale se o texto for muito grande para o botão (ex: Limpar)
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
        
        # Desenha a mão de navegação
        mp_draw.draw_landmarks(img, handLms_nav, mp_hands.HAND_CONNECTIONS, estilo_ponto, estilo_linha)

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
        
        # Lógica de Clique (Pinça)
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
        
        if pygame_ok:
            draw_button(img, BTN_MENU_JOGO, "Jogo")
        else:
            draw_button(img, BTN_MENU_JOGO, "Jogo (OFF)", bg_color=(100,100,100)) # Botão desabilitado

        # Checa cliques nos botões
        if click_detected:
            if is_cursor_in_rect(cursor_pos, BTN_MENU_GESTOS):
                current_screen = "GESTOS"
            
            elif is_cursor_in_rect(cursor_pos, BTN_MENU_DESENHO):
                current_screen = "DESENHO"
                canvas.fill(0) # Limpa o canvas
                last_draw_point = None
            
            elif is_cursor_in_rect(cursor_pos, BTN_MENU_FOTO):
                current_screen = "FOTO"
                photo_app_state = "IDLE" # Reseta o estado da câmera
            
            elif is_cursor_in_rect(cursor_pos, BTN_MENU_JOGO) and pygame_ok:
                current_screen = "JOGO"
                # Reseta o Jogo
                game_state = "START"
                game_bird_y = HEIGHT // 2
                game_pipes = []
                game_score = 0
                game_start_time = time.time()
                if pygame_ok and pygame.mixer.music.get_busy() == False:
                    pygame.mixer.music.play(-1) # Toca a música do jogo em loop

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
        # Desenha a nova paleta de cores
        # Note que a cor do botão (bg_color) é a cor que ele representa
        draw_button(img, BTN_DRAW_RED, "R", bg_color=(0,0,255), is_selected=(current_color == (0,0,255)))
        draw_button(img, BTN_DRAW_GREEN, "G", bg_color=(0,255,0), is_selected=(current_color == (0,255,0)))
        draw_button(img, BTN_DRAW_BLUE, "B", bg_color=(255,0,0), is_selected=(current_color == (255,0,0)))
        draw_button(img, BTN_DRAW_WHITE, "W", bg_color=(255,255,255), is_selected=(current_color == (255,255,255)))
        draw_button(img, BTN_DRAW_ERASER, "X", bg_color=(100,100,100), is_selected=(current_color == (0,0,0)))
        
        draw_button(img, BTN_DRAW_CLEAR, "Limpar")
        draw_button(img, BTN_VOLTAR, "Voltar")
        
        # Lógica de clique para os novos botões
        if click_detected:
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
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_WHITE):
                current_color = (255, 255, 255)
                current_thickness = 12
            
            # Botão Borracha (Pincel preto e grosso)
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_ERASER):
                current_color = (0, 0, 0) # Cor do canvas
                current_thickness = 40 # Borracha mais grossa
            
            # Botão Limpar Tela
            elif is_cursor_in_rect(cursor_pos, BTN_DRAW_CLEAR):
                canvas.fill(0) # Preenche o canvas com preto
        
        # Proteção para não desenhar sobre a UI
        # Verifica se o cursor está sobre QUALQUER botão da tela
        is_on_ui = (
            is_cursor_in_rect(cursor_pos, BTN_VOLTAR) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_RED) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_GREEN) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_BLUE) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_WHITE) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_ERASER) or
            is_cursor_in_rect(cursor_pos, BTN_DRAW_CLEAR)
        )
        
        # Gesto de desenhar: Pinca (polegar + indicador)
        # Não desenha se a pinça estiver em cima de um botão
        can_draw = is_pinching and not is_on_ui

        if can_draw:
            if last_draw_point is None: # Se é o começo de um traço
                last_draw_point = cursor_pos # Apenas marque o início
            
            # Usa a espessura da ferramenta atual
            # Desenha a linha (grossa e suave)
            cv2.line(canvas, last_draw_point, cursor_pos, current_color, current_thickness) # Usa espessura
            last_draw_point = cursor_pos # Atualiza o último ponto
        else:
            last_draw_point = None # Pinca solta, pare de desenhar (reseta o último ponto)
        
        # Combina o canvas com a imagem da câmera
        img = cv2.addWeighted(img, 1.0, canvas, 1.0, 0)
        
        # (Lógica de clique do Voltar foi movida para cima, junto com os outros botões)
    
    # --- TELA DA CÂMERA (FOTO) ---
    elif current_screen == "FOTO":
        overlay_text = ""
        countdown_text = ""
        
        # Lógica de estado da Câmera (copiado de testefoto.py)
        if photo_app_state == "IDLE":
            overlay_text = "Mostre a mao aberta para comecar"
            # Mão aberta (usando dedos_nav da mão principal)
            if dedos_nav == [1, 1, 1, 1, 1]:
                photo_app_state = "ARMING"
                photo_timer_start_time = time.time()
                print("Mão aberta detectada! Armando em 2s...")

        elif photo_app_state == "ARMING": 
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
                filename = os.path.join(output_folder, f"foto_{int(time.time())}.jpg")
                img_clean_flipped = cv2.flip(img_raw, 1) # Salva a imagem limpa e flipada
                cv2.imwrite(filename, img_clean_flipped) 
                print(f"Foto salva: {filename}")
                
                photo_app_state = "CAPTURED"
                photo_flash_start_time = time.time()
        
        # Estado de feedback (flash)
        if photo_app_state == "CAPTURED":
            overlay_text = "FOTO CAPTURADA!"
            if time.time() - photo_flash_start_time < 0.5:
                cv2.rectangle(img, (0, 0), (WIDTH, HEIGHT), (255, 255, 255), -1)
            else:
                # --- MUDANÇA: Voltar ao Menu automaticamente ---
                current_screen = "MENU" # Nova lógica (volta ao menu)
                # --- Fim da mudança ---
                
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
            
    # --- TELA DO JOGO ---
    elif current_screen == "JOGO" and pygame_ok:
        
        # --- MUDANÇA: Fundo azul claro (MAIS SUAVE) ---
        light_blue_bg = np.full_like(img, (255, 230, 200)) # BGR: Azul claro
        # 70% câmera, 30% fundo azul
        img = cv2.addWeighted(img, 0.7, light_blue_bg, 0.3, 0)
        # --- Fim da mudança ---
        
        # Lógica do Jogo (copiado de testeseguir.py)
        if game_state == "START":
            cv2.putText(img, "FLAPPY DEDO", (WIDTH // 2 - 270, HEIGHT // 2 - 150), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 255, 255), 8)
            # --- MUDANÇA: Texto de instrução atualizado ---
            cv2.putText(img, "Junte os dedos (pinca) para PULAR", (WIDTH // 2 - 400, HEIGHT // 2 + 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)
            # --- Fim da mudança ---
            
            # --- MUDANÇA: Usar click_detected para começar ---
            # if is_pinching: # Usa a pinça da mão principal
            if click_detected: # Mais consistente
            # --- Fim da mudança ---
                game_state = "PLAYING"
                game_start_time = time.time()
                game_score = 0
                game_pipes = []
                game_bird_y = HEIGHT // 2
                game_bird_vel = 0

        elif game_state == "PLAYING":
            
            # --- MUDANÇA: Dificuldade Progressiva ---
            # A cada 5 pontos, o jogo fica mais rápido e o vão diminui
            difficulty_level = game_score // 5
            # Velocidade aumenta em 2 a cada 5 pontos, com limite de 26
            current_pipe_speed = min(26, game_pipe_speed + difficulty_level * 2) 
            # Vão diminui 10px a cada 5 pontos, com limite de 160px
            current_pipe_gap = max(160, game_pipe_gap - difficulty_level * 10) 
            # --- Fim da mudança ---

            # --- MUDANÇA: Lógica de Pulo (Flap) ---
            # O "pulo" é acionado pela PINÇA (is_pinching)
            # (Usamos click_detected para pular só UMA VEZ por pinça)
            if click_detected: # Usar o clique (pinçar e soltar) é mais justo
                 game_bird_vel = game_lift # Dá o impulso para cima
            # --- Fim da mudança ---
            
            # --- MUDANÇA: Controle com Física (Gravidade) ---
            # Controle: O pássaro segue o indicador (cursor_pos[1] é o Y)
            # game_bird_y = cursor_pos[1] # <--- REMOVIDO (muito fácil)
            
            # Aplicar gravidade e velocidade
            game_bird_vel += game_gravity
            game_bird_y += int(game_bird_vel)
            # --- Fim da mudança ---
            
            # Lógica dos Canos
            current_time = time.time()
            if current_time - game_last_pipe_time > game_pipe_interval:
                # --- MUDANÇA: Usa o vão dinâmico ---
                h = random.randint(150, HEIGHT - 150 - current_pipe_gap)
                # --- Fim da mudança ---
                game_pipes.append({"x": WIDTH, "height": h, "color": (0, 200, 0)})
                game_last_pipe_time = current_time

            new_pipes = []
            for pipe in game_pipes:
                # --- MUDANÇA: Usa a velocidade dinâmica ---
                pipe["x"] -= current_pipe_speed
                # --- Fim da mudança ---
                
                x, h = pipe["x"], pipe["height"]
                color = pipe["color"]
                
                # Cano de cima
                cv2.rectangle(img, (x, 0), (x + game_pipe_width, h), color, -1)
                # Cano de baixo
                # --- MUDANÇA: Usa o vão dinâmico ---
                cv2.rectangle(img, (x, h + current_pipe_gap), (x + game_pipe_width, HEIGHT), color, -1)

                # Colisão com canos
                if (game_bird_y - game_bird_radius < h or game_bird_y + game_bird_radius > h + current_pipe_gap) and \
                   (WIDTH // 2 + game_bird_radius > x and WIDTH // 2 - game_bird_radius < x + game_pipe_width) and \
                   game_state != "GAME_OVER": # Adiciona o check para rodar só uma vez
                # --- Fim da mudança ---
                    
                    # --- MUDANÇA: Tirar foto ao perder ---
                    filename = os.path.join(output_folder, f"foto_gameover_{int(time.time())}.jpg")
                    img_clean_flipped = cv2.flip(img_raw, 1) # Salva a imagem limpa
                    cv2.imwrite(filename, img_clean_flipped) 
                    print(f"Foto Game Over salva: {filename}")
                    # --- Fim da mudança ---

                    game_state = "GAME_OVER"
                    if pygame_ok: pygame.mixer.music.stop()

                # Pontuação
                if x + game_pipe_width < (WIDTH // 2 - game_bird_radius) and "counted" not in pipe:
                    game_score += 1
                    pipe["counted"] = True
                    if ponto_sound:
                        ponto_sound.play()

                if x + game_pipe_width > 0:
                    new_pipes.append(pipe)
            game_pipes = new_pipes

            # Checa colisão com teto/chão
            if (game_bird_y - game_bird_radius <= 0 or game_bird_y + game_bird_radius >= HEIGHT) and game_state != "GAME_OVER":
                
                # --- MUDANÇA: Tirar foto ao perder ---
                filename = os.path.join(output_folder, f"foto_gameover_{int(time.time())}.jpg")
                img_clean_flipped = cv2.flip(img_raw, 1) # Salva a imagem limpa
                cv2.imwrite(filename, img_clean_flipped) 
                print(f"Foto Game Over salva: {filename}")
                # --- Fim da mudança ---

                game_state = "GAME_OVER"
                if pygame_ok: pygame.mixer.music.stop()
            
            # Desenha Pássaro (posição X fixa)
            cv2.circle(img, (WIDTH // 2, game_bird_y), game_bird_radius, (0, 255, 255), -1)
            
            # Pontos
            cv2.putText(img, f"Pontos: {game_score}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (0,0,0), 8)
            cv2.putText(img, f"Pontos: {game_score}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)

        elif game_state == "GAME_OVER":
            cv2.putText(img, "GAME OVER", (WIDTH // 2 - 280, HEIGHT // 2 - 150), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 255), 10)
            cv2.putText(img, f"Pontos: {game_score}", (WIDTH // 2 - 120, HEIGHT // 2 + 50), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)
            
            # --- MUDANÇA: Lógica de botões (em vez de pinça) ---
            draw_button(img, BTN_GAME_RESTART, "REINICIAR", bg_color=(0, 200, 0))
            
            # Checa o clique (pinça) nos botões
            if click_detected:
                if is_cursor_in_rect(cursor_pos, BTN_GAME_RESTART):
                    # Reinicia o jogo
                    game_state = "PLAYING"
                    game_start_time = time.time()
                    game_score = 0
                    game_pipes = []
                    game_bird_y = HEIGHT // 2
                    game_bird_vel = 0
                    if pygame_ok: pygame.mixer.music.play(-1) # Reinicia a música
                
                # O botão Sair (BTN_VOLTAR) será checado abaixo na UI
            
            # --- Fim da mudança ---

        # Botão Voltar (sempre visível no jogo, incluindo Game Over)
        draw_button(img, BTN_VOLTAR, "Sair")
        
        # --- MUDANÇA: Movido o clique do "Sair" para fora do "GAME_OVER" ---
        # --- assim ele funciona no PLAYING e no GAME_OVER ---
        if click_detected and is_cursor_in_rect(cursor_pos, BTN_VOLTAR):
            current_screen = "MENU"
            if pygame_ok: pygame.mixer.music.stop() # Para a música ao sair

    # ------------------- Desenhar cursor (sempre por cima) -------------------
    # Apenas desenha o cursor se uma mão for detectada
    if results.multi_hand_landmarks:
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