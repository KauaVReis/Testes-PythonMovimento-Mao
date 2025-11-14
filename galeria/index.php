<?php
// --------------------------------------------------------
// 1. CONFIGURAÇÃO DE CONEXÃO COM O BANCO DE DADOS
// --------------------------------------------------------
$DB_CONFIG = [
    'host' => 'localhost',
    'user' => 'root', 
    'password' => '', // Senha vazia (padrão XAMPP/WAMP)
    'database' => 'flappy_game_db'
];

$podium_scores = [];
$gallery_images = [];
$db_error = null;

try {
    // Tenta estabelecer a conexão
    $conn = new mysqli(
        $DB_CONFIG['host'], 
        $DB_CONFIG['user'], 
        $DB_CONFIG['password'], 
        $DB_CONFIG['database']
    );

    // Verifica se houve erro na conexão
    if ($conn->connect_error) {
        throw new Exception("Falha na conexão com o MySQL: " . $conn->connect_error);
    }

    // --------------------------------------------------------
    // 2. BUSCA NO BANCO DE DADOS (DUAS BUSCAS SEPARADAS)
    // --------------------------------------------------------
    
    // QUERY 1: PÓDIO (Top 3 scores do Jogo)
    $sql_podium = "SELECT score, image_path FROM highscores WHERE score > 0 ORDER BY score DESC LIMIT 3";
    $result_podium = $conn->query($sql_podium);
    
    if ($result_podium && $result_podium->num_rows > 0) {
        while($row = $result_podium->fetch_assoc()) {
            $podium_scores[] = $row;
        }
    }

    // QUERY 2: GALERIA (Fotos normais/desenho, score = 0)
    $sql_gallery = "SELECT score, image_path FROM highscores WHERE score = 0 ORDER BY id DESC LIMIT 50";
    $result_gallery = $conn->query($sql_gallery);
    
    if ($result_gallery && $result_gallery->num_rows > 0) {
        while($row = $result_gallery->fetch_assoc()) {
            $gallery_images[] = $row;
        }
    }

    $conn->close();

} catch (Exception $e) {
    $db_error = $e->getMessage();
    error_log("Erro no Ranking: " . $db_error);
}
?>

<!DOCTYPE html>
<html lang="pt-br">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BiliBili HandCam - Pódio</title>
    <link rel="stylesheet" href="style.css"> 
</head>

<body>

    <header class="main-header">
        <nav class="main-nav">
            <!-- MUDANÇA: Título novo -->
            <a href="index.php" class="nav-logo">📸 BiliBili HandCam</a>
            <ul class="nav-list">
                <li><a href="#ranking">Pódio (Jogo)</a></li>
                <li><a href="#galeria">Galeria (Fotos)</a></li>
                <!-- MUDANÇA: Link agora aponta para o ranking por 'top' -->
                <li><a href="ranking.php?sort=top">Ranking Geral</a></li>
            </ul>
        </nav>
    </header>

    <main>
        
        <?php if ($db_error): ?>
            <p class="empty-message error">❌ Erro de Conexão com o Banco de Dados. Verifique se o XAMPP (MySQL) está ligado.</p>
        <?php endif; ?>

        <section id="ranking" class="ranking-section">
            <h2 class="section-title">⭐ PÓDIO - FLAPPY DEDO ⭐</h2>

            <div class="podium-container" id="ranking-container">
                
                <?php if (count($podium_scores) > 0): ?>
                    
                    <?php 
                        // Prepara os 3 scores (ou placeholders se houver menos de 3)
                        $rank_1 = $podium_scores[0] ?? null;
                        $rank_2 = $podium_scores[1] ?? null;
                        $rank_3 = $podium_scores[2] ?? null;
                    ?>

                    <!-- Pódio 2 (Esquerda) -->
                    <div class="podium-item rank-2">
                        <?php if ($rank_2): $image_path = "../fotos/" . $rank_2['image_path']; ?>
                            <div class="podium-image-box">
                                <img src="<?php echo $image_path; ?>" alt="Score <?php echo $rank_2['score']; ?>" class="podium-image">
                            </div>
                            <div class="item-info">
                                <span class="rank">2º</span>
                                <p class="votes"><?php echo $rank_2['score']; ?> Pontos</p>
                            </div>
                        <?php endif; ?>
                    </div>

                    <!-- Pódio 1 (Centro) -->
                    <div class="podium-item rank-1">
                        <?php if ($rank_1): $image_path = "../fotos/" . $rank_1['image_path']; ?>
                            <div class="podium-image-box">
                                <img src="<?php echo $image_path; ?>" alt="Score <?php echo $rank_1['score']; ?>" class="podium-image">
                            </div>
                            <div class="item-info">
                                <span class="rank">1º</span>
                                <p class="votes"><?php echo $rank_1['score']; ?> Pontos</p>
                            </div>
                        <?php endif; ?>
                    </div>

                    <!-- Pódio 3 (Direita) -->
                    <div class="podium-item rank-3">
                         <?php if ($rank_3): $image_path = "../fotos/" . $rank_3['image_path']; ?>
                            <div class="podium-image-box">
                                <img src="<?php echo $image_path; ?>" alt="Score <?php echo $rank_3['score']; ?>" class="podium-image">
                            </div>
                            <div class="item-info">
                                <span class="rank">3º</span>
                                <p class="votes"><?php echo $rank_3['score']; ?> Pontos</p>
                            </div>
                        <?php endif; ?>
                    </div>

                <?php elseif (!$db_error): ?>
                    <p class="empty-message">Nenhum placar do jogo registrado ainda. Jogue para aparecer no pódio!</p>
                <?php endif; ?>
            </div>

        </section>

        <section id="galeria" class="gallery-section">
            <h2 class="section-title">GALERIA (Fotos da Câmera e Desenho)</h2>
            <div class="gallery-container">
                <?php if (count($gallery_images) > 0): ?>
                    <?php foreach ($gallery_images as $item): ?>
                        <?php $image_path = "../fotos/" . $item['image_path']; ?> 
                        <!-- MUDANÇA: Adicionado <a> para download -->
                        <div class="gallery-item">
                            <img src="<?php echo $image_path; ?>" alt="Foto da Galeria" class="gallery-image">
                            <!-- Botão de Download Adicionado -->
                            <a href="<?php echo $image_path; ?>" download class="download-btn" title="Baixar foto">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                            </a>
                        </div>
                        <!-- Fim da Mudança -->
                    <?php endforeach; ?>
                <?php elseif (!$db_error): ?>
                    <p class="empty-message">Nenhuma foto da câmera ou desenho foi salva ainda.</p>
                <?php endif; ?>
            </div>
        </section>
    </main>

    <!-- Modal (Lightbox) para clicar nas imagens -->
    <div id="imageModal" class="modal">
        <span class="close-button">&times;</span>
        <img class="modal-content" id="modalImage">
        <!-- MUDANÇA: Wrapper para caption e botão de download -->
        <div class="modal-bottom-bar">
            <div id="caption" class="caption-text"></div>
            <!-- Botão de Download no Modal -->
            <a href="#" id="modalDownloadBtn" class="download-btn-modal" download="<?php echo $item['image_path']; ?>">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                <span>Baixar</span>
            </a>
        </div>
        <!-- Fim da Mudança -->
    </div>
    
    <script src="script.js"></script>
</body>

</html>