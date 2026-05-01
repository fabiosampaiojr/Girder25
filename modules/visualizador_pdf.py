# =============================================================================
# visualizador_pdf.py
# -----------------------------------------------------------------------------
# Módulo de visualização de arquivos PDF integrado à interface PyQt6.
#
# Fornece a classe PDFViewer, um QDialog completo com suporte a:
#   - Renderização de alta qualidade via PyMuPDF (fitz)
#   - Zoom interativo (botões, slider, combo box e Ctrl + scroll)
#   - Navegação por páginas (anterior/próxima e salto direto via QSpinBox)
#   - Arrastar a página com o botão esquerdo do mouse
#   - Ajuste automático à largura ou à página inteira
#   - Barra de status com número de página e dimensões em pixels
#
# Também contém a classe DemoApplication (QMainWindow), utilizada como
# aplicação de demonstração standalone para testes locais do visualizador.
#
# Dependências externas: PyMuPDF (fitz), PyQt6
# =============================================================================

import sys
import fitz  # PyMuPDF — biblioteca de leitura e renderização de PDFs
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QScrollArea,
    QDialog, QSizePolicy, QMessageBox, QSlider, QComboBox, QSpinBox
)
from PyQt6.QtGui import QPixmap, QImage, QWheelEvent, QMouseEvent, QCursor
from PyQt6.QtCore import Qt, QPoint, QTimer, QEvent
import os


class PDFViewer(QDialog):
    """
    Diálogo de visualização de PDF com zoom completo e barras de rolagem.

    Renderiza páginas do PDF como imagens de alta resolução dentro de uma
    QScrollArea, permitindo navegação, zoom e arraste com o mouse.

    Parâmetros
    ----------
    pdf_path : str
        Caminho absoluto para o arquivo .pdf a ser aberto.
    window_title : str, opcional
        Título exibido na barra da janela (padrão: "Visualizador PDF").
    """

    def __init__(self, pdf_path, window_title="Visualizador PDF"):
        super().__init__()

        # Caminho do PDF e título da janela
        self.pdf_path = pdf_path
        self.window_title = window_title

        # Controle de página
        self.current_page = 0       # Índice da página atual (base 0)
        self.doc = None             # Objeto fitz.Document, inicializado em load_pdf()
        self.total_pages = 0        # Total de páginas do documento

        # Parâmetros de zoom
        self.zoom_factor = 1.0      # Fator de zoom atual (1.0 = 100%)
        self.min_zoom = 0.25        # Zoom mínimo permitido (25%)
        self.max_zoom = 5.0         # Zoom máximo permitido (500%)
        self.zoom_step = 0.1        # Incremento/decremento por passo de zoom

        # Fator de qualidade base: multiplica o zoom para renderização nítida
        self.base_quality = 3

        # Controle de arrastar com o mouse
        self.is_dragging = False            # Flag: indica se o usuário está arrastando
        self.drag_start_pos = QPoint()      # Posição global do mouse no início do arraste
        self.scroll_start_pos = QPoint()    # Posição das barras de scroll no início do arraste

        # Configuração da janela
        self.setWindowTitle(f"{window_title} - {os.path.basename(pdf_path)}")
        self.setMinimumSize(800, 600)

        # ── Layout Principal ──────────────────────────────────────────────────
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Barra de ferramentas (navegação + controles de zoom)
        toolbar = self.create_toolbar()
        layout.addLayout(toolbar)

        # Container que envolve a área de visualização do PDF
        view_container = QWidget()
        view_layout = QVBoxLayout(view_container)
        view_layout.setContentsMargins(0, 0, 0, 0)

        # ── Área de Rolagem ───────────────────────────────────────────────────
        # setWidgetResizable(False) é obrigatório para que as barras de rolagem
        # apareçam quando a imagem renderizada for maior que a área visível.
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Widget interno que hospeda a imagem renderizada
        self.image_widget = QWidget()
        self.image_widget.setMouseTracking(True)
        self.image_widget.installEventFilter(self)  # Intercepta eventos de mouse/scroll

        # Label onde o QPixmap da página é exibido
        self.image_label = QLabel(self.image_widget)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image_label.setMouseTracking(True)
        self.image_label.installEventFilter(self)  # Necessário para capturar arrastar sobre a imagem

        # Layout do widget de imagem (sem margens para aproveitar todo o espaço)
        image_layout = QVBoxLayout(self.image_widget)
        image_layout.addWidget(self.image_label)
        image_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area.setWidget(self.image_widget)
        view_layout.addWidget(self.scroll_area)

        layout.addWidget(view_container)

        # ── Barra de Status ───────────────────────────────────────────────────
        status_layout = QHBoxLayout()

        self.status_label = QLabel()                                      # Ex.: "Página 1 de 10"
        self.zoom_label = QLabel(f"Zoom: {int(self.zoom_factor * 100)}%") # Ex.: "Zoom: 100%"
        self.dimensions_label = QLabel()                                   # Ex.: "1240 × 1754 px"

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.dimensions_label)
        status_layout.addStretch()
        status_layout.addWidget(self.zoom_label)

        layout.addLayout(status_layout)

        self.setLayout(layout)

        # ── Timer de Renderização ─────────────────────────────────────────────
        # Evita re-renderizações excessivas durante interações rápidas (ex.: scroll de zoom).
        # A renderização só ocorre após o último disparo do timer (single-shot).
        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self.render_page)

        # Carrega o arquivo PDF e exibe a primeira página
        self.load_pdf()

        # Conecta as barras de rolagem ao slot de atualização de posição
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self.update_scroll_position)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.update_scroll_position)

    def create_toolbar(self):
        """
        Constrói e retorna o QHBoxLayout da barra de ferramentas.

        Contém: botões de navegação (anterior/próxima/ir para página),
        controles de zoom (−, slider, +, 100%, combo box),
        botões de ajuste (largura/página) e botão fechar.
        """
        toolbar = QHBoxLayout()
        toolbar.setSpacing(5)

        # ── Navegação de Páginas ──────────────────────────────────────────────
        self.prev_btn = QPushButton("← Anterior")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)  # Desabilitado na primeira página

        self.next_btn = QPushButton("Próxima →")
        self.next_btn.clicked.connect(self.next_page)

        page_label = QLabel("Página:")
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(100)  # Atualizado dinamicamente após load_pdf()
        self.page_spin.valueChanged.connect(self.go_to_page)

        toolbar.addWidget(self.prev_btn)
        toolbar.addWidget(self.next_btn)
        toolbar.addWidget(page_label)
        toolbar.addWidget(self.page_spin)

        toolbar.addStretch()  # Separa navegação dos controles de zoom

        # ── Controles de Zoom ─────────────────────────────────────────────────
        zoom_label = QLabel("Zoom:")

        zoom_out_btn = QPushButton("-")
        zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_out_btn.setFixedWidth(30)
        zoom_out_btn.setToolTip("Diminuir zoom (Ctrl + Scroll Down)")

        # Slider de ajuste fino de zoom (valores em porcentagem inteira)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(int(self.min_zoom * 100))   # 25
        self.zoom_slider.setMaximum(int(self.max_zoom * 100))   # 500
        self.zoom_slider.setValue(int(self.zoom_factor * 100))  # 100
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.valueChanged.connect(self.zoom_slider_changed)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_in_btn.setFixedWidth(30)
        zoom_in_btn.setToolTip("Aumentar zoom (Ctrl + Scroll Up)")

        zoom_reset_btn = QPushButton("100%")
        zoom_reset_btn.clicked.connect(self.zoom_reset)
        zoom_reset_btn.setFixedWidth(60)
        zoom_reset_btn.setToolTip("Zoom padrão (100%)")

        # Combo box com níveis de zoom pré-definidos
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["25%", "50%", "75%", "100%", "125%", "150%", "200%", "300%", "400%", "500%"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.currentTextChanged.connect(self.zoom_combo_changed)
        self.zoom_combo.setFixedWidth(80)

        # ── Ajuste Automático ─────────────────────────────────────────────────
        fit_width_btn = QPushButton("Largura")
        fit_width_btn.clicked.connect(self.fit_to_width)
        fit_width_btn.setToolTip("Ajustar página à largura da janela")
        fit_width_btn.setFixedWidth(70)

        fit_page_btn = QPushButton("Página")
        fit_page_btn.clicked.connect(self.fit_to_page)
        fit_page_btn.setToolTip("Ajustar página inteira na janela")
        fit_page_btn.setFixedWidth(70)

        # ── Fechar ────────────────────────────────────────────────────────────
        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.close)
        close_btn.setFixedWidth(70)

        # Adiciona todos os controles à toolbar
        toolbar.addWidget(zoom_label)
        toolbar.addWidget(zoom_out_btn)
        toolbar.addWidget(self.zoom_slider)
        toolbar.addWidget(zoom_in_btn)
        toolbar.addWidget(zoom_reset_btn)
        toolbar.addWidget(self.zoom_combo)
        toolbar.addWidget(fit_width_btn)
        toolbar.addWidget(fit_page_btn)
        toolbar.addWidget(close_btn)

        return toolbar

    def load_pdf(self):
        """
        Abre o arquivo PDF informado em self.pdf_path via PyMuPDF.

        Configura o QSpinBox de páginas com o total real do documento
        e exibe automaticamente a primeira página (índice 0).
        Em caso de falha (arquivo inexistente ou PDF inválido), exibe
        um QMessageBox crítico e fecha o diálogo.
        """
        try:
            if not os.path.exists(self.pdf_path):
                raise FileNotFoundError(f"Arquivo não encontrado: {self.pdf_path}")

            self.doc = fitz.open(self.pdf_path)
            self.total_pages = len(self.doc)

            # Atualiza o limite máximo do SpinBox com o total real de páginas
            self.page_spin.setMaximum(self.total_pages)

            # Exibe a primeira página ao abrir
            self.display_page(0)

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao carregar PDF:\n{str(e)}")
            self.close()

    def display_page(self, page_num):
        """
        Navega até a página especificada e dispara a renderização.

        Parâmetros
        ----------
        page_num : int
            Índice da página (base 0). Valores fora do intervalo são ignorados.

        Observação
        ----------
        O QSpinBox é atualizado com sinais bloqueados para evitar loops
        de chamada recursiva entre go_to_page() e display_page().
        """
        if not self.doc or page_num < 0 or page_num >= self.total_pages:
            return

        self.current_page = page_num

        # Atualiza o SpinBox sem disparar o sinal valueChanged
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page_num + 1)  # SpinBox usa base 1 (exibição ao usuário)
        self.page_spin.blockSignals(False)

        self.render_page()

    def render_page(self):
        """
        Renderiza a página atual com o zoom aplicado e atualiza a interface.

        Fluxo de renderização:
            1. Obtém a página fitz na posição self.current_page.
            2. Calcula o zoom total = base_quality × zoom_factor para alta resolução.
            3. Aplica uma fitz.Matrix de escala uniforme.
            4. Converte o Pixmap fitz em QImage (RGB888 ou RGBA8888).
            5. Converte QImage em QPixmap e exibe no image_label.
            6. Ajusta o tamanho fixo de image_widget ao pixmap gerado.
            7. Atualiza labels de status, dimensões e zoom.
            8. Aguarda 50 ms antes de resetar as barras de rolagem
               (necessário para garantir que o layout foi processado).
        """
        if not self.doc:
            return

        try:
            page = self.doc[self.current_page]

            # Zoom total: base_quality garante nitidez independente do fator de zoom
            total_zoom = self.base_quality * self.zoom_factor

            # Matriz de transformação para escala uniforme (x, y)
            mat = fitz.Matrix(total_zoom, total_zoom)

            # Renderiza a página como bitmap; alpha=False gera imagem RGB pura
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Seleciona o formato QImage adequado ao número de canais
            if pix.n == 3:  # Imagem RGB (3 canais)
                img_format = QImage.Format.Format_RGB888
            else:           # Imagem RGBA (4 canais, com transparência)
                img_format = QImage.Format.Format_RGBA8888

            img = QImage(pix.samples, pix.width, pix.height, pix.stride, img_format)

            # Converte QImage para QPixmap (formato nativo de exibição do Qt)
            pixmap = QPixmap.fromImage(img)

            self.image_label.setPixmap(pixmap)

            # Ajusta o tamanho do widget contentor ao tamanho do pixmap
            # para que a QScrollArea saiba quando exibir barras de rolagem
            self.image_widget.setFixedSize(pixmap.size())

            # Atualiza labels de status
            self.dimensions_label.setText(f"{pix.width} × {pix.height} px")
            self.status_label.setText(f"Página {self.current_page + 1} de {self.total_pages}")
            self.zoom_label.setText(f"Zoom: {int(self.zoom_factor * 100)}%")

            # Habilita/desabilita botões de navegação conforme a página atual
            self.prev_btn.setEnabled(self.current_page > 0)
            self.next_btn.setEnabled(self.current_page < self.total_pages - 1)

            # Reseta as barras de rolagem após o processamento do layout (50 ms de delay)
            QTimer.singleShot(50, self.reset_scrollbars)

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao exibir página:\n{str(e)}")

    def reset_scrollbars(self):
        """
        Reposiciona as barras de rolagem horizontal e vertical para o início (0, 0).

        Chamada via QTimer.singleShot após render_page() para garantir que
        o layout já foi calculado antes de reposicionar as barras.
        """
        self.scroll_area.horizontalScrollBar().setValue(0)
        self.scroll_area.verticalScrollBar().setValue(0)

    def update_scroll_position(self):
        """
        Slot conectado às barras de rolagem horizontal e vertical.

        Reservado para uso futuro (ex.: exibir coordenadas de scroll na barra
        de status ou sincronizar com um mapa de miniatura da página).
        """
        pass

    def eventFilter(self, obj, event):
        """
        Filtro de eventos global que intercepta interações de mouse sobre
        image_widget e image_label.

        Comportamentos implementados:
        - Wheel + Ctrl  → zoom_in() ou zoom_out() conforme direção do scroll.
        - MousePress    → inicia arraste; registra posição inicial do mouse e
                          das barras de rolagem; muda cursor para mão fechada.
        - MouseMove     → calcula delta em relação ao início do arraste e
                          atualiza as barras de rolagem proporcionalmente.
        - MouseRelease  → finaliza arraste; restaura cursor padrão.
        """
        # Zoom via Ctrl + roda do mouse
        if event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self.zoom_in()
                else:
                    self.zoom_out()
                return True  # Evento consumido; não propaga para a scroll area

        # Início do arraste: botão esquerdo pressionado
        elif event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_dragging = True
                self.drag_start_pos = event.globalPosition().toPoint()
                # Salva a posição atual das barras para cálculo do delta
                self.scroll_start_pos = QPoint(
                    self.scroll_area.horizontalScrollBar().value(),
                    self.scroll_area.verticalScrollBar().value()
                )
                self.image_label.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                return True

        # Movimento do mouse durante arraste
        elif event.type() == QEvent.Type.MouseMove:
            if self.is_dragging:
                current_pos = event.globalPosition().toPoint()
                delta = current_pos - self.drag_start_pos

                h_scroll = self.scroll_area.horizontalScrollBar()
                v_scroll = self.scroll_area.verticalScrollBar()

                # Subtrai o delta para que a imagem "siga" o mouse naturalmente
                h_scroll.setValue(self.scroll_start_pos.x() - delta.x())
                v_scroll.setValue(self.scroll_start_pos.y() - delta.y())
                return True

        # Fim do arraste: botão esquerdo solto
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_dragging = False
                self.image_label.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                return True

        # Demais eventos seguem o comportamento padrão do Qt
        return super().eventFilter(obj, event)

    def prev_page(self):
        """Navega para a página anterior, se não estiver na primeira."""
        if self.current_page > 0:
            self.display_page(self.current_page - 1)

    def next_page(self):
        """Navega para a próxima página, se não estiver na última."""
        if self.current_page < self.total_pages - 1:
            self.display_page(self.current_page + 1)

    def go_to_page(self, page_num):
        """
        Navega diretamente para a página indicada pelo QSpinBox.

        Parâmetros
        ----------
        page_num : int
            Número da página em base 1 (valor exibido ao usuário).
            Convertido internamente para base 0 antes de chamar display_page().
        """
        actual_page = page_num - 1  # Converte de base 1 (UI) para base 0 (fitz)
        if 0 <= actual_page < self.total_pages:
            self.display_page(actual_page)

    def apply_zoom(self):
        """
        Sincroniza os controles visuais de zoom (slider e combo box) com
        self.zoom_factor e re-renderiza a página atual.

        Bloqueia sinais dos controles durante a atualização para evitar
        chamadas recursivas entre os slots de zoom.
        """
        # Atualiza o slider sem propagar o sinal valueChanged
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(self.zoom_factor * 100))
        self.zoom_slider.blockSignals(False)

        # Atualiza a combo box sem propagar o sinal currentTextChanged
        self.zoom_combo.blockSignals(True)
        self.zoom_combo.setCurrentText(f"{int(self.zoom_factor * 100)}%")
        self.zoom_combo.blockSignals(False)

        # Re-renderiza a página com o novo fator de zoom
        self.display_page(self.current_page)

    def zoom_in(self):
        """Aumenta o zoom em um passo (zoom_step), respeitando o limite máximo."""
        if self.zoom_factor < self.max_zoom:
            self.zoom_factor = min(self.zoom_factor + self.zoom_step, self.max_zoom)
            self.apply_zoom()

    def zoom_out(self):
        """Diminui o zoom em um passo (zoom_step), respeitando o limite mínimo."""
        if self.zoom_factor > self.min_zoom:
            self.zoom_factor = max(self.zoom_factor - self.zoom_step, self.min_zoom)
            self.apply_zoom()

    def zoom_reset(self):
        """Restaura o zoom para 100% (zoom_factor = 1.0)."""
        self.zoom_factor = 1.0
        self.apply_zoom()

    def zoom_slider_changed(self, value):
        """
        Slot do slider de zoom.

        Parâmetros
        ----------
        value : int
            Novo valor do slider (em porcentagem inteira, ex.: 150 = 150%).
        """
        self.zoom_factor = value / 100.0
        self.apply_zoom()

    def zoom_combo_changed(self, text):
        """
        Slot da combo box de zoom.

        Converte o texto selecionado (ex.: "150%") para float e aplica o zoom.
        Ignora valores inválidos silenciosamente.

        Parâmetros
        ----------
        text : str
            Texto da opção selecionada na combo box (ex.: "100%").
        """
        try:
            zoom_percent = int(text.replace("%", ""))
            self.zoom_factor = zoom_percent / 100.0
            self.apply_zoom()
        except ValueError:
            pass  # Texto inválido; nenhuma ação necessária

    def fit_to_width(self):
        """
        Calcula e aplica o zoom necessário para que a largura da página
        preencha toda a largura disponível na QScrollArea.

        O cálculo converte a largura da página de pontos PDF (pt) para pixels
        de tela usando a razão 72 DPI (PDF) / 96 DPI (tela), divide pelo
        base_quality para compensar a escala interna de renderização e,
        por fim, clipa o resultado nos limites [min_zoom, max_zoom].
        """
        if not self.doc:
            return

        try:
            page = self.doc[self.current_page]

            page_width_pt = page.rect.width
            scroll_width = self.scroll_area.viewport().width() - 20  # Margem de segurança

            # Conversão: pontos PDF → pixels de tela (72 pt = 96 px ⟹ fator = 72/96)
            pixels_per_point = 72.0 / 96.0
            page_width_px = page_width_pt * pixels_per_point

            required_zoom = scroll_width / page_width_px

            # Compensa o fator de qualidade base já aplicado na renderização
            required_zoom = required_zoom / self.base_quality

            self.zoom_factor = max(self.min_zoom, min(required_zoom, self.max_zoom))
            self.apply_zoom()

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao ajustar à largura:\n{str(e)}")

    def fit_to_page(self):
        """
        Calcula e aplica o zoom necessário para que a página inteira
        (largura e altura) caiba dentro da área visível da QScrollArea.

        Usa o menor fator entre o zoom que ajusta a largura e o que ajusta
        a altura, garantindo que a página não seja cortada em nenhuma dimensão.
        """
        if not self.doc:
            return

        try:
            page = self.doc[self.current_page]

            page_width_pt = page.rect.width
            page_height_pt = page.rect.height

            scroll_width = self.scroll_area.viewport().width() - 20
            scroll_height = self.scroll_area.viewport().height() - 20

            # Conversão de pontos para pixels de tela
            pixels_per_point = 72.0 / 96.0
            page_width_px = page_width_pt * pixels_per_point
            page_height_px = page_height_pt * pixels_per_point

            zoom_width = scroll_width / page_width_px
            zoom_height = scroll_height / page_height_px

            # O menor dos dois zooms garante que toda a página seja visível
            required_zoom = min(zoom_width, zoom_height)

            # Compensa o fator de qualidade base
            required_zoom = required_zoom / self.base_quality

            self.zoom_factor = max(self.min_zoom, min(required_zoom, self.max_zoom))
            self.apply_zoom()

        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao ajustar à página:\n{str(e)}")

    def closeEvent(self, event):
        """
        Sobrescreve o evento de fechamento da janela para liberar o documento PDF.

        Chama fitz.Document.close() para garantir que os recursos de arquivo
        sejam liberados antes de destruir o widget.
        """
        if self.doc:
            self.doc.close()
        event.accept()


# =============================================================================
# DemoApplication
# -----------------------------------------------------------------------------
# Janela principal de demonstração standalone, usada exclusivamente para
# testes locais do PDFViewer fora do contexto do sistema principal.
# Não é instanciada pela aplicação em produção.
# =============================================================================

class DemoApplication(QMainWindow):
    """
    Aplicação de demonstração com múltiplos exemplos de abertura de PDFs.

    Exibe uma interface com botões para abrir PDFs de exemplo pré-definidos
    e um botão para gerar um PDF de demonstração com PyMuPDF.
    Utilizada somente para testes locais do módulo visualizador_pdf.py.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Demonstração do Visualizador PDF")
        self.setGeometry(100, 100, 700, 500)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()

        # ── Cabeçalho ─────────────────────────────────────────────────────────
        header_label = QLabel("📚 Visualizador PDF Avançado")
        header_label.setStyleSheet("""
            font-size: 24px; 
            font-weight: bold; 
            padding: 20px;
            color: #2c3e50;
            background: linear-gradient(to right, #3498db, #2ecc71);
            border-radius: 10px;
            margin: 10px;
        """)
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header_label)

        # ── Instruções / Lista de Funcionalidades ─────────────────────────────
        instructions = QLabel(
            "<h3>🚀 Funcionalidades Implementadas:</h3>"
            "<table width='100%'>"
            "<tr><td>• ✅ Zoom com Ctrl+Roda do Mouse</td><td>• ✅ Barras de Rolagem Automáticas</td></tr>"
            "<tr><td>• ✅ Controles de Zoom (+/-/Slider)</td><td>• ✅ Arraste com Mouse</td></tr>"
            "<tr><td>• ✅ Ajuste à Largura/Página</td><td>• ✅ Navegação entre Páginas</td></tr>"
            "<tr><td>• ✅ Títulos Personalizados</td><td>• ✅ Renderização de Alta Qualidade</td></tr>"
            "<tr><td>• ✅ Status com Dimensões</td><td>• ✅ Interface Intuitiva</td></tr>"
            "</table>"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("""
            padding: 20px; 
            background: #f8f9fa; 
            border-radius: 10px;
            border: 2px solid #dee2e6;
            margin: 10px;
        """)
        main_layout.addWidget(instructions)

        # ── Botões de Exemplo ─────────────────────────────────────────────────
        examples_label = QLabel("📄 Abrir Exemplos:")
        examples_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 20px;")
        main_layout.addWidget(examples_label)

        buttons_grid = QVBoxLayout()

        # Linha 1 de botões
        row1 = QHBoxLayout()
        btn1 = self.create_example_button("📖 Manual do Usuário", "Manual Completo do Sistema",
                                         "manual_usuario", "Manual do Usuário")
        btn2 = self.create_example_button("⚡ Guia Rápido", "Instruções Básicas de Uso",
                                         "guia_rapido", "Guia Rápido")
        row1.addWidget(btn1)
        row1.addWidget(btn2)
        buttons_grid.addLayout(row1)

        # Linha 2 de botões
        row2 = QHBoxLayout()
        btn3 = self.create_example_button("🔧 Documentação Técnica", "Especificações Técnicas",
                                         "documentacao_tecnica", "Documentação Técnica")
        btn4 = self.create_example_button("📋 FAQ e Ajuda", "Perguntas Frequentes",
                                         "faq_ajuda", "FAQ e Ajuda")
        row2.addWidget(btn3)
        row2.addWidget(btn4)
        buttons_grid.addLayout(row2)

        main_layout.addLayout(buttons_grid)

        # ── Botão Criar PDF de Exemplo ────────────────────────────────────────
        create_btn = QPushButton("🆕 Criar PDF de Exemplo para Teste")
        create_btn.clicked.connect(self.create_example_pdf)
        create_btn.setStyleSheet("""
            QPushButton {
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
                background: linear-gradient(to right, #9b59b6, #e74c3c);
                color: white;
                border-radius: 8px;
                margin: 20px;
            }
            QPushButton:hover {
                background: linear-gradient(to right, #8e44ad, #c0392b);
            }
        """)
        main_layout.addWidget(create_btn)

        # ── Rodapé com Dicas de Uso ───────────────────────────────────────────
        footer = QLabel("""
            <center>
            <p><b>Dicas de Uso:</b></p>
            <p>• Use <b>Ctrl + Roda do Mouse</b> para zoom rápido</p>
            <p>• Arraste com <b>botão esquerdo</b> para navegar quando ampliado</p>
            <p>• Use <b>barras de rolagem</b> ou <b>setas do teclado</b> para navegar</p>
            </center>
        """)
        footer.setStyleSheet("""
            padding: 15px;
            background: #2c3e50;
            color: white;
            border-radius: 10px;
            margin: 10px;
        """)
        main_layout.addWidget(footer)

        central_widget.setLayout(main_layout)

    def create_example_button(self, text, tooltip, pdf_name, window_title):
        """
        Cria e retorna um QPushButton estilizado para abrir um PDF de exemplo.

        Parâmetros
        ----------
        text : str
            Texto exibido no botão (pode incluir emoji).
        tooltip : str
            Texto do tooltip ao passar o mouse sobre o botão.
        pdf_name : str
            Nome base do arquivo PDF a ser procurado (sem extensão).
        window_title : str
            Título da janela PDFViewer ao abrir o arquivo.
        """
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.clicked.connect(lambda: self.open_pdf_example(pdf_name, window_title))
        btn.setStyleSheet("""
            QPushButton {
                padding: 12px;
                font-size: 13px;
                background: linear-gradient(to right, #3498db, #2980b9);
                color: white;
                border-radius: 6px;
                margin: 5px;
            }
            QPushButton:hover {
                background: linear-gradient(to right, #2980b9, #1c5a7a);
            }
        """)
        return btn

    def open_pdf_example(self, pdf_name, window_title):
        """
        Tenta abrir um PDF de exemplo pelo nome base fornecido.

        Busca sequencialmente pelos nomes: '{pdf_name}.pdf', 'exemplo.pdf'
        e 'manual.pdf' no diretório do script. Se nenhum for encontrado,
        oferece ao usuário a opção de gerar um PDF de demonstração.

        Parâmetros
        ----------
        pdf_name : str
            Nome base do arquivo PDF (sem extensão).
        window_title : str
            Título da janela PDFViewer caso o arquivo seja encontrado.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Lista de nomes candidatos em ordem de prioridade
        possible_files = [
            f"{pdf_name}.pdf",
            "exemplo.pdf",
            "manual.pdf"
        ]

        pdf_path = None
        for filename in possible_files:
            test_path = os.path.join(script_dir, filename)
            if os.path.exists(test_path):
                pdf_path = test_path
                break

        if pdf_path:
            viewer = PDFViewer(pdf_path, window_title)
            viewer.exec()
        else:
            # Arquivo não encontrado: oferece criar um PDF de demonstração
            response = QMessageBox.question(
                self, "PDF não encontrado",
                f"Arquivo '{pdf_name}.pdf' não encontrado.\n\n"
                f"Deseja criar um PDF de exemplo para teste?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if response == QMessageBox.StandardButton.Yes:
                self.create_example_pdf()

    def create_example_pdf(self):
        """
        Gera um arquivo 'exemplo.pdf' com 5 páginas de demonstração via PyMuPDF.

        Cada página contém: título, linha decorativa, texto descritivo das
        funcionalidades, elementos gráficos (retângulo, círculo, triângulo)
        e rodapé. A página 3 (índice 2) inclui uma grade de referência.

        Após a criação, o PDF é aberto automaticamente no PDFViewer.
        O arquivo é salvo no mesmo diretório do script.
        """
        try:
            from datetime import datetime

            script_dir = os.path.dirname(os.path.abspath(__file__))
            pdf_path = os.path.join(script_dir, "exemplo.pdf")

            doc = fitz.open()

            # Cria 5 páginas no formato A4 (595 × 842 pt)
            for page_num in range(5):
                page = doc.new_page(width=595, height=842)

                # Título da página
                title = f"PÁGINA DE DEMONSTRAÇÃO {page_num + 1}/5"
                page.insert_text((50, 50), title, fontsize=24, color=(0.2, 0.2, 0.6))

                # Linha decorativa horizontal
                page.draw_line((50, 85), (545, 85), color=(0.8, 0.2, 0.2), width=2)

                # Conteúdo textual com lista de funcionalidades
                content = f"""
                Este é um PDF de exemplo criado para demonstrar todas as funcionalidades
                do visualizador PDF avançado.

                Data de criação: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

                Funcionalidades testáveis:

                1. Zoom com Ctrl + Roda do Mouse
                   - Pressione Ctrl e use a roda para zoom

                2. Barras de Rolagem Automáticas
                   - Aparecem quando a imagem é maior que a área visível

                3. Controles de Zoom
                   - Botões + e -
                   - Slider de ajuste fino
                   - Combo box com zoom pré-definido

                4. Navegação
                   - Botões Anterior/Próxima
                   - Campo para ir para página específica

                5. Ajustes Automáticos
                   - "Largura": Ajusta à largura da janela
                   - "Página": Ajusta a página inteira

                6. Arraste com Mouse
                   - Clique e arraste para navegar quando ampliado

                7. Informações de Status
                   - Dimensões da imagem
                   - Número da página atual
                   - Nível de zoom atual
                """

                page.insert_text((50, 100), content, fontsize=11)

                # ── Elementos Gráficos Ilustrativos ───────────────────────────
                y_offset = 350

                # Retângulo vermelho-claro
                page.draw_rect((50, y_offset, 200, y_offset + 100),
                              color=(0.9, 0.6, 0.6), fill=(0.9, 0.6, 0.6))
                page.insert_text((70, y_offset + 40), "Elemento Gráfico 1", fontsize=10)

                # Círculo verde-claro
                page.draw_circle((350, y_offset + 50), 45,
                                color=(0.6, 0.9, 0.6), fill=(0.6, 0.9, 0.6))
                page.insert_text((320, y_offset + 50), "Elemento 2", fontsize=10)

                # Triângulo azul-claro
                points = [(500, y_offset), (550, y_offset + 100), (450, y_offset + 100)]
                page.draw_polygon(points, color=(0.6, 0.6, 0.9), fill=(0.6, 0.6, 0.9))
                page.insert_text((480, y_offset + 40), "Elemento 3", fontsize=10)

                # Rodapé da página
                footer = f"Visualizador PDF - Demonstração - Página {page_num + 1} de 5"
                page.insert_text((50, 800), footer, fontsize=9, color=(0.4, 0.4, 0.4))

                # Grade de referência exibida apenas na página 3 (índice 2)
                if page_num == 2:
                    for i in range(0, 600, 50):
                        page.draw_line((i, 0), (i, 842), color=(0.9, 0.9, 0.9), width=0.5)
                        page.draw_line((0, i), (595, i), color=(0.9, 0.9, 0.9), width=0.5)

            # Salva e fecha o documento gerado
            doc.save(pdf_path)
            doc.close()

            # Abre automaticamente o PDF recém-criado
            viewer = PDFViewer(pdf_path, "PDF de Exemplo")
            viewer.exec()

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao criar PDF:\n{str(e)}")


# =============================================================================
# Ponto de entrada — execução standalone para testes
# =============================================================================

def main():
    app = QApplication(sys.argv)

    # Estilo visual padrão da aplicação de demonstração
    app.setStyle("Fusion")

    window = DemoApplication()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
