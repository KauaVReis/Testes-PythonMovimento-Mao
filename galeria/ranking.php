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

$all_scores = [];
$db_error = null;

// --- MUDANÇA: Lógica de Ordenação ---
// Verifica o parâmetro na URL. O padrão é 'top'.
$sort_mode = $_GET['sort'] ?? 'top'; 
$page_title = "Ranking Geral";

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
    // 2. BUSCA NO BANCO DE DADOS (TODOS OS SCORES)
    // --------------------------------------------------------
    
    // Busca apenas scores MAIORES que 0
    $sql_all = "SELECT score, image_path, created_at FROM highscores WHERE score > 0";

    // Adiciona a ordenação baseada no $sort_mode
    if ($sort_mode === 'recent') {
        $sql_all .= " ORDER BY id DESC"; // 'id DESC' = Mais recentes primeiro
        $page_title = "Ranking (Últimos Jogos)";
    } else {
        $sql_all .= " ORDER BY score DESC, id DESC"; // 'score DESC' = Top scores
        $page_title = "Ranking (Top Scores)";
    }

    $result_all = $conn->query($sql_all);
    
    if ($result_all && $result_all->num_rows > 0) {
        while($row = $result_all->fetch_assoc()) {
            $all_scores[] = $row;
        }
    }

    $conn->close();

} catch (Exception $e) {
    $db_error = $e->getMessage();
    error_log("Erro no Ranking Geral: " . $db_error);
}
// --- Fim da Mudança ---
?>

<!DOCTYPE html>
<html lang="pt-br">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <!-- MUDANÇA: Título dinâmico -->
    <title>BiliBili HandCam - <?php echo $page_title; ?></title>
    <link rel="stylesheet" href="style.css"> 
</head>

<body>

    <header class="main-header">
        <nav class="main-nav">
            <!-- Título novo -->
            <a href="index.php" class="nav-logo">📸 BiliBili HandCam</a>
            <ul class="nav-list">
                <li><a href="index.php#ranking">Pódio (Jogo)</a></li>
                <li><a href="index.php#galeria">Galeria (Fotos)</a></li>
                <!-- MUDANÇA: Botão Ativo -->
                <li><a href="ranking.php?sort=top" class="<?php echo ($sort_mode === 'top' ? 'active' : ''); ?>">Ranking Geral</a></li>
            </ul>
        </nav>
    </header>

    <main>
        
        <?php if ($db_error): ?>
            <p class="empty-message error">❌ Erro de Conexão com o Banco de Dados. Verifique se o XAMPP (MySQL) está ligado.</p>
        <?php endif; ?>

        <section id="ranking-geral" class="ranking-geral-section">
            <h2 class="section-title">🏆 RANKING GERAL (HISTÓRICO) 🏆</h2>

            <!-- MUDANÇA: Botões de Filtro/Toggle -->
            <div class="sort-toggle-container">
                <a href="ranking.php?sort=top" class="sort-toggle-btn <?php echo ($sort_mode === 'top' ? 'active' : ''); ?>">
                    ⭐ Top Scores
                </a>
                <a href="ranking.php?sort=recent" class="sort-toggle-btn <?php echo ($sort_mode === 'recent' ? 'active' : ''); ?>">
                    🕒 Últimos Jogos (Histórico)
                </a>
            </div>
            <!-- Fim da Mudança -->

            <!-- Wrapper para a tabela rolar em telas pequenas -->
            <div class="table-wrapper">
                <table class="ranking-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Pontuação</th>
                            <th>Foto (Clique para ver)</th>
                            <th>Data e Hora (Histórico)</th>
                            <th>Baixar</th> <!-- Nova coluna -->
                        </tr>
                    </thead>
                    <tbody>
                        <?php if (count($all_scores) > 0): ?>
                            <?php foreach ($all_scores as $index => $item): ?>
                                <tr>
                                    <td class="rank-number"><?php echo $index + 1; ?></td>
                                    <td class="player-score"><?php echo $item['score']; ?> Pontos</td>
                                    <td class="player-image">
                                        <img src="../fotos/<?php echo $item['image_path']; ?>" alt="Score <?php echo $item['score']; ?>" class="table-image">
                                    </td>
                                    <td class="player-date"><?php echo date("d/m/Y H:i", strtotime($item['created_at'])); ?></td>
                                    <!-- MUDANÇA: Botão de Download na Tabela -->
                                    <td class="player-download">
                                        <a href="../fotos/<?php echo $item['image_path']; ?>" download="<?php echo $item['image_path']; ?>" class="download-btn-table" title="Baixar foto">
                                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                                        </a>
                                    </td>
                                    <!-- Fim da Mudança -->
                                </tr>
                            <?php endforeach; ?>
                        <?php elseif (!$db_error): ?>
                            <tr>
                                <td colspan="5" class="empty-message">Nenhum placar do jogo registrado ainda.</td>
                            </tr>
                        <?php endif; ?>
                    </tbody>
                </table>
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
            <a href="#" id="modalDownloadBtn" class="download-btn-modal" download>
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                <span>Baixar</span>
            </a>
        </div>
        <!-- Fim da Mudança -->
    </div>
    
    <script src="script.js"></script>
</body>

</html>