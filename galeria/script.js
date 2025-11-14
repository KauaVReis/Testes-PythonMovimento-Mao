document.addEventListener('DOMContentLoaded', function() {
    // 1. Seleção de elementos do Modal
    var modal = document.getElementById("imageModal");
    var modalImg = document.getElementById("modalImage");
    var captionText = document.getElementById("caption");
    var closeButton = document.querySelector(".close-button");

    // 2. MUDANÇA: Seleciona as imagens do PÓDIO, GALERIA e da NOVA TABELA
    var images = document.querySelectorAll('.podium-image, .gallery-item img, .table-image');

    // 3. Adiciona o evento de clique em todas as imagens
    images.forEach(function(img) {
        img.onclick = function(){
            modal.style.display = "block";
            modalImg.src = this.src;
            
            // Tenta obter a pontuação do atributo alt
            var scoreText = "Foto da Galeria"; // Padrão
            if (this.alt && this.alt.includes("Score")) {
                 scoreText = this.alt.replace("Score", "Pontuação");
            }
            
            captionText.innerHTML = scoreText;
        }
    });

    // 4. Função para fechar o Modal ao clicar no X
    closeButton.onclick = function() { 
        modal.style.display = "none";
    }

    // 5. Função para fechar o Modal ao clicar no fundo preto (fora da imagem)
    modal.onclick = function(event) {
        if (event.target === modal) {
            modal.style.display = "none";
        }
    }
    
    // 6. Função para fechar o Modal ao pressionar a tecla ESC
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && modal.style.display === "block") {
            modal.style.display = "none";
        }
    });
});