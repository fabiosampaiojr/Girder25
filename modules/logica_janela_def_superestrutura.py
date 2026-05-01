# ============================================================================
# Girder25 - logica_janela_def_superestrutura.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da janela de definição do sistema estrutural longitudinal.
# ============================================================================

import os
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QTableWidgetItem, QVBoxLayout, QLabel,
    QFileDialog, QPushButton, QHBoxLayout, QDoubleSpinBox, QWidget,
    QButtonGroup, QFormLayout, QSpinBox, QHeaderView
)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.janela_def_superestrutura import Ui_janela_def_superestrutura
from modules.desenho_dcl import desenhar_dcl
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.Calculadora_Vaos_Otimos import CalculadoraVaosOtimos
from modules.logica_janela_memorial import LogicaJanelaMemorial
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path

# Mapeamento entre texto exibido na combo e chave interna de processamento
MAPA_TIPOS = {
    "Isostática: Múltiplos Vãos Biapoioados": "biapoiada",
    "Isostática: Biapoiada com Balanço": "isostatica_em_balanco",
    "Hiperestática: Vão Contínuo sem Balanço": "hiperestatica_sem_balanco",
    "Hiperestática: Vão Contínuo com Balanço": "hiperestatica_com_balanco"
}

# ============================================================================
# 1. DIÁLOGOS SECUNDÁRIOS
# ============================================================================

class DialogoExportacao(QDialog):
    """Diálogo para escolher o formato de exportação (PNG ou DXF)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Formato de Exportação")
        self.setFixedSize(250, 100)
        self.formato_escolhido = None

        layout = QVBoxLayout(self)
        lbl = QLabel("Escolha o formato para salvar o diagrama:")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

        h_layout = QHBoxLayout()
        btn_png = QPushButton("Imagem (.PNG)")
        btn_dxf = QPushButton("CAD (.DXF)")

        btn_png.clicked.connect(lambda: self.selecionar_formato("png"))
        btn_dxf.clicked.connect(lambda: self.selecionar_formato("dxf"))

        h_layout.addWidget(btn_png)
        h_layout.addWidget(btn_dxf)
        layout.addLayout(h_layout)

    def selecionar_formato(self, formato):
        self.formato_escolhido = formato
        self.accept()


class DialogoCalculoVaos(QDialog):
    """
    Diálogo para entrada dos parâmetros do dimensionamento automático
    via CalculadoraVaosOtimos. Exibe os resultados e oferece memorial de cálculo.
    """
    def __init__(self, tipo_interno, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calculadora de Vãos Ótimos")
        self.setMinimumWidth(380)
        
        self.tipo_interno = tipo_interno
        self.vaos_mapeados = []
        self.html_memorial = ""

        self.layout_principal = QVBoxLayout(self)

        # Formulário de entrada
        self.widget_form = QWidget()
        layout_form = QFormLayout(self.widget_form)

        self.spin_comprimento = QDoubleSpinBox()
        self.spin_comprimento.setMinimum(0.5)
        self.spin_comprimento.setMaximum(100000.0)
        self.spin_comprimento.setDecimals(1)
        self.spin_comprimento.setSingleStep(0.5)
        self.spin_comprimento.setValue(25.0)
        self.spin_comprimento.setSuffix(" m")
        layout_form.addRow("Comprimento Total da Ponte:", self.spin_comprimento)

        self.spin_n_vaos = None
        if self.tipo_interno == "biapoiada":
            self.spin_n_vaos = QSpinBox()
            self.spin_n_vaos.setMinimum(1)
            self.spin_n_vaos.setMaximum(100)
            self.spin_n_vaos.setValue(2)
            layout_form.addRow("Número de Vãos:", self.spin_n_vaos)

        self.btn_obter = QPushButton("Obter Distribuição Inicial Recomendada")
        self.btn_obter.clicked.connect(self.executar_calculo)
        layout_form.addRow(self.btn_obter)

        # Tela de resultado (inicialmente oculta)
        self.widget_resultado = QWidget()
        layout_resultado = QVBoxLayout(self.widget_resultado)

        lbl_sucesso = QLabel("✅ Distribuição Inicial Recomendada Calculada com Sucesso!")
        lbl_sucesso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = lbl_sucesso.font()
        font.setBold(True)
        lbl_sucesso.setFont(font)

        h_layout = QHBoxLayout()
        self.btn_memorial = QPushButton("Memorial de Cálculo")
        self.btn_ok = QPushButton("OK")

        self.btn_memorial.clicked.connect(self.abrir_memorial)
        self.btn_ok.clicked.connect(self.accept)

        h_layout.addWidget(self.btn_memorial)
        h_layout.addWidget(self.btn_ok)

        layout_resultado.addWidget(lbl_sucesso)
        layout_resultado.addSpacing(15)
        layout_resultado.addLayout(h_layout)

        self.layout_principal.addWidget(self.widget_form)
        self.layout_principal.addWidget(self.widget_resultado)
        self.widget_resultado.setVisible(False)

    def executar_calculo(self):
        """
        Executa o motor de otimização e converte os resultados para o formato
        esperado pela tabela de vãos.
        """
        calc = CalculadoraVaosOtimos()
        comp = self.spin_comprimento.value()
        n_vaos = self.spin_n_vaos.value() if self.spin_n_vaos else 1

        try:
            resultado = calc.otimizar_vaos(self.tipo_interno, comp, n_vaos)
            _, html = calc.obter_relatorios()
            self.html_memorial = html

            dist = resultado.distribuicao
            sys_val = resultado.sistema_estrutural.value

            # Mapeamento para ordem exibida na tabela
            if sys_val == "isostatica_em_balanco":
                self.vaos_mapeados = [dist[1].comprimento, dist[0].comprimento]
            elif sys_val == "hiperestatica_sem_balanco":
                self.vaos_mapeados = [dist[1].comprimento, dist[0].comprimento]
            elif sys_val == "hiperestatica_com_balanco":
                self.vaos_mapeados = [dist[2].comprimento, dist[1].comprimento, dist[0].comprimento]
            elif sys_val == "biapoiada":
                self.vaos_mapeados = [d.comprimento for d in dist]

            # Exibe a tela de resultado
            self.widget_form.setVisible(False)
            self.widget_resultado.setVisible(True)

        except Exception as e:
            QMessageBox.critical(self, "Erro no Cálculo",
                                 f"Ocorreu um erro no processamento analítico:\n{str(e)}")

    def abrir_memorial(self):
        """Abre o memorial de cálculo em uma janela específica."""
        dlg = LogicaJanelaMemorial("Memorial de Cálculo – Vãos Ótimos", self.html_memorial, self)
        dlg.exec()


# ============================================================================
# 2. CONTROLADOR PRINCIPAL DA JANELA
# ============================================================================

class LogicaDefinirSuperestrutura(QDialog, Ui_janela_def_superestrutura):
    """
    Controlador da janela de definição do sistema estrutural (vãos e lajes).
    Permite entrada manual ou cálculo automático da distribuição de vãos.
    """

    def __init__(self, gerenciador):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador
        self.fig_atual = None

        self.vaos_calculados_auto = None
        self.html_memorial_auto = None

        # Configuração do campo de laje de transição
        self.input_laje.setMinimum(0.01)
        self.input_laje.setMaximum(100000.0)
        self.input_laje.setDecimals(1)
        self.input_laje.setSingleStep(0.05)
        self.input_laje.setSuffix(" m")
        self.input_laje.setValue(2.50)

        # Área de desenho
        self.layout_desenho = QVBoxLayout(self.desenho)
        self.lbl_aguardando = QLabel("Aguardando Geração do Desenho")
        self.lbl_aguardando.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_desenho.addWidget(self.lbl_aguardando)
        self.exportar.setEnabled(False)

        # Radio buttons: modo automático / manual
        self.grupo_modo = QButtonGroup(self)
        self.grupo_modo.addButton(self.radio_automatico)
        self.grupo_modo.addButton(self.radio_manual)
        self.radio_automatico.setChecked(True)

        # Conexões dos widgets
        self.radio_automatico.toggled.connect(self._atualizar_modo)
        self.radio_manual.toggled.connect(self._atualizar_modo)
        self.calcular.clicked.connect(self._abrir_dialogo_calculo)
        self.input_tipo.currentIndexChanged.connect(self._on_tipo_changed)
        self.check_laje.toggled.connect(self.toggle_laje)
        self.atualizar.clicked.connect(self.processar_desenho)
        self.exportar.clicked.connect(self.abrir_dialogo_exportacao)
        self.confirmar.clicked.connect(self.salvar_dados)
        self.cancelar.clicked.connect(self.reject)
        self.manual.clicked.connect(self.abrir_manual)

        # Inicializa a tabela de vãos
        self._construir_tabela()

        # Se já existir uma superestrutura definida, carrega seus dados
        self.carregar_dados_existentes()

    # -------------------------------------------------------------------------
    # Eventos de janela
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        """Libera a figura do Matplotlib para evitar vazamento de memória."""
        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Controle de estado da interface
    # -------------------------------------------------------------------------
    def _on_tipo_changed(self):
        """Reseta cálculos automáticos quando o tipo estrutural é alterado."""
        self.vaos_calculados_auto = None
        self.html_memorial_auto = None
        self._construir_tabela()

    def _atualizar_modo(self):
        """Habilita/desabilita botões conforme seleção Manual/Automático."""
        is_auto = self.radio_automatico.isChecked()
        self.calcular.setEnabled(is_auto)
        self._construir_tabela()

    def _construir_tabela(self):
        """
        Reconstrói a tabela de vãos de acordo com o modo atual e a existência
        de dados calculados.
        """
        self.tabela_config.blockSignals(True)
        self.tabela_config.setRowCount(0)

        tipo_interno = self._obter_tipo_interno(self.input_tipo.currentText())
        is_auto = self.radio_automatico.isChecked()

        # Modo automático ainda sem cálculo: exibe apenas mensagem
        if is_auto and not self.vaos_calculados_auto:
            self.tabela_config.setColumnCount(1)
            self.tabela_config.horizontalHeader().setVisible(False)
            self.tabela_config.verticalHeader().setVisible(False)
            self.tabela_config.insertRow(0)

            item = QTableWidgetItem("Aguardando Cálculos...")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.tabela_config.setItem(0, 0, item)
            self.tabela_config.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.tabela_config.blockSignals(False)
            self.exportar.setEnabled(False)
            return

        # Modo manual ou automático com dados prontos
        self.tabela_config.setColumnCount(2)
        self.tabela_config.horizontalHeader().setVisible(False)
        self.tabela_config.verticalHeader().setVisible(False)

        header = self.tabela_config.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)

        # Determina os rótulos de acordo com o tipo estrutural
        rotulos = []
        if tipo_interno == "hiperestatica_sem_balanco":
            rotulos = ["Vão Central", "Vão Externo"]
        elif tipo_interno == "hiperestatica_com_balanco":
            rotulos = ["Vão Central", "Vão Externo", "Vão Balanço"]
        elif tipo_interno == "isostatica_em_balanco":
            rotulos = ["Vão Central", "Vão Balanço"]
        elif tipo_interno == "biapoiada":
            if self.vaos_calculados_auto:
                rotulos = [f"Vão {i+1}" for i in range(len(self.vaos_calculados_auto))]
            else:
                rotulos = ["Vão 1"]

        # Preenche cada linha com rótulo e spinbox
        for i, rotulo in enumerate(rotulos):
            valor_padrao = 10.00
            if self.vaos_calculados_auto and i < len(self.vaos_calculados_auto):
                valor_padrao = self.vaos_calculados_auto[i]
            self.adicionar_linha_tabela(rotulo, valor_padrao, is_auto=is_auto)

        # Botão para adicionar novos vãos (apenas em modo manual biapoiado)
        if tipo_interno == "biapoiada" and not is_auto:
            self._adicionar_linha_botao()

        self.tabela_config.blockSignals(False)
        self.exportar.setEnabled(False)

    def _abrir_dialogo_calculo(self):
        """Abre o diálogo de cálculo automático dos vãos."""
        tipo_interno = self._obter_tipo_interno(self.input_tipo.currentText())
        dlg = DialogoCalculoVaos(tipo_interno, parent=self)

        if dlg.exec():
            self.vaos_calculados_auto = dlg.vaos_mapeados
            self.html_memorial_auto = dlg.html_memorial
            self._construir_tabela()

    # -------------------------------------------------------------------------
    # Manipulação da tabela de vãos
    # -------------------------------------------------------------------------
    def adicionar_linha_tabela(self, rotulo, valor_padrao=10.00, row=None, is_auto=False):
        """Insere uma linha composta por rótulo e campo numérico para um vão."""
        if row is None:
            row = self.tabela_config.rowCount()
            self.tabela_config.insertRow(row)

        item_rotulo = QTableWidgetItem(rotulo)
        item_rotulo.setFlags(Qt.ItemFlag.ItemIsEnabled)
        fonte = item_rotulo.font()
        fonte.setBold(True)
        item_rotulo.setFont(fonte)

        spin = self._criar_spinbox_vazio(valor_padrao)

        if is_auto:
            spin.setReadOnly(True)
            spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            spin.setStyleSheet("""
                QDoubleSpinBox[readOnly="true"] {
                    background-color: #2d2d2d;
                    color: #ffffff;
                    border: 1px solid #555;
                }
            """)

        self.tabela_config.setCellWidget(row, 1, spin)
        self.tabela_config.setItem(row, 0, item_rotulo)
        self.tabela_config.setRowHeight(row, spin.sizeHint().height() + 4)

    def _criar_spinbox_vazio(self, valor_padrao=10.00):
        """Fábrica de QDoubleSpinBox padronizados para comprimento de vão."""
        spin = QDoubleSpinBox(self.tabela_config)
        spin.setMinimum(0.01)
        spin.setMaximum(100000.0)
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setSuffix(" m")
        spin.setValue(valor_padrao)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return spin

    def _adicionar_linha_botao(self):
        """Adiciona o botão 'Adicionar Vão' no final da tabela (modo manual)."""
        row = self.tabela_config.rowCount()
        self.tabela_config.insertRow(row)
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        btn = QPushButton("Adicionar Vão")
        btn.setAutoDefault(False)
        btn.setStyleSheet("QPushButton { padding: 2px; }")
        btn.clicked.connect(self._adicionar_novo_vao)

        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.tabela_config.setCellWidget(row, 0, container)
        self.tabela_config.setItem(row, 1, QTableWidgetItem(""))
        self.tabela_config.setRowHeight(row, btn.sizeHint().height() + 4)

    def _adicionar_novo_vao(self):
        """Cria um novo campo de vão na tabela (modo manual, estrutura biapoiada)."""
        num_vaos = 0
        for r in range(self.tabela_config.rowCount()):
            widget = self.tabela_config.cellWidget(r, 1)
            if isinstance(widget, QDoubleSpinBox):
                num_vaos += 1
        proximo_num = num_vaos + 1
        row_botao = self.tabela_config.rowCount() - 1
        self.tabela_config.insertRow(row_botao)
        self.adicionar_linha_tabela(f"Vão {proximo_num}", row=row_botao)

    def toggle_laje(self, estado):
        """Habilita/desabilita o campo de laje de transição."""
        self.input_laje.setEnabled(estado)
        self.label_laje.setEnabled(estado)
        if estado and self.input_laje.value() == 0.0:
            self.input_laje.setValue(2.50)

    # -------------------------------------------------------------------------
    # Validação, processamento de desenho e salvamento
    # -------------------------------------------------------------------------
    def carregar_dados_existentes(self):
        """Restaura os dados de uma superestrutura já salva no gerenciador."""
        sup = self.gerenciador.get_superestrutura()
        if sup:
            self.input_tipo.blockSignals(True)
            idx = self.input_tipo.findText(sup.tipo)
            if idx >= 0:
                self.input_tipo.setCurrentIndex(idx)
            self.input_tipo.blockSignals(False)

            # Força o modo manual preservando os valores originais
            self.radio_manual.blockSignals(True)
            self.radio_automatico.blockSignals(True)
            self.radio_manual.setChecked(True)
            self.radio_manual.blockSignals(False)
            self.radio_automatico.blockSignals(False)

            self._atualizar_modo()

            self.vaos_calculados_auto = sup.vaos
            self._construir_tabela()

            if sup.laje_transicao:
                self.check_laje.setChecked(True)
                self.input_laje.setValue(float(sup.laje_transicao))
            else:
                self.check_laje.setChecked(False)

            self.processar_desenho()
        else:
            self.toggle_laje(False)

    def _obter_tipo_interno(self, texto_selecionado):
        """Converte o texto da combo para a chave interna de tipo estrutural."""
        tipo = MAPA_TIPOS.get(texto_selecionado)
        if tipo is not None:
            return tipo

        # Fallback para garantir compatibilidade com textos antigos
        if "Múltiplos Vãos" in texto_selecionado:
            return "biapoiada"
        elif "Biapoiada com Balanço" in texto_selecionado:
            return "isostatica_em_balanco"
        elif "Vão Contínuo sem Balanço" in texto_selecionado:
            return "hiperestatica_sem_balanco"
        elif "Vão Contínuo com Balanço" in texto_selecionado:
            return "hiperestatica_com_balanco"
        return "biapoiada"

    def validar_entradas(self):
        """
        Verifica se os dados da tabela são coerentes antes de desenhar ou salvar.
        Retorna (vaos, laje_transicao) ou None se houver erro.
        """
        is_auto = self.radio_automatico.isChecked()

        if is_auto and not self.vaos_calculados_auto:
            QMessageBox.warning(
                self, "Ação Necessária",
                "Você selecionou o modo Automático. É necessário clicar em "
                "'Calcular Vão Ótimo' e definir os vãos antes de prosseguir."
            )
            return None

        vaos = []
        tipo_interno = self._obter_tipo_interno(self.input_tipo.currentText())

        for r in range(self.tabela_config.rowCount()):
            widget = self.tabela_config.cellWidget(r, 1)
            if not isinstance(widget, QDoubleSpinBox):
                continue
            valor = widget.value()
            if valor <= 0:
                item_rotulo = self.tabela_config.item(r, 0).text() if self.tabela_config.item(r, 0) else f"Linha {r+1}"
                QMessageBox.warning(self, "Erro de Validação",
                                    f"O '{item_rotulo}' deve ser estritamente positivo (>0).")
                return None
            vaos.append(valor)

        if tipo_interno == "biapoiada" and len(vaos) == 0:
            QMessageBox.warning(self, "Erro de Validação", "Adicione pelo menos um Vão.")
            return None

        laje_val = False
        if self.check_laje.isChecked():
            laje_val = self.input_laje.value()
            if laje_val <= 0:
                QMessageBox.warning(self, "Erro de Validação",
                                    "Laje de Transição deve possuir extensão positiva.")
                return None

        return vaos, laje_val

    def processar_desenho(self):
        """Gera o diagrama DCL com base nos vãos e laje informados."""
        dados = self.validar_entradas()
        if not dados:
            return

        vaos, laje_transicao = dados
        tipo_interno = self._obter_tipo_interno(self.input_tipo.currentText())

        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None

        # Remove qualquer canvas antigo do layout
        for i in reversed(range(self.layout_desenho.count())):
            widget = self.layout_desenho.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        try:
            self.fig_atual = desenhar_dcl(tipo_interno, vaos, laje_transicao)
            canvas = FigureCanvas(self.fig_atual)
            self.layout_desenho.addWidget(canvas)
            self.exportar.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Erro na Renderização",
                                 f"Ocorreu um erro interno na geração visual:\n{str(e)}")

    def salvar_dados(self):
        """Valida e persiste a superestrutura no gerenciador de dados."""
        dados = self.validar_entradas()
        if not dados:
            return

        vaos, laje_transicao = dados
        tipo_texto = self.input_tipo.currentText()
        self.gerenciador.definir_superestrutura(tipo_texto, vaos, laje_transicao)
        self.accept()

    def abrir_dialogo_exportacao(self):
        """Oferece exportação do diagrama como imagem PNG ou arquivo DXF."""
        if not self.fig_atual:
            return

        dlg = DialogoExportacao(self)
        if dlg.exec():
            formato = dlg.formato_escolhido

            if formato == "png":
                caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Imagem", "", "Imagens PNG (*.png)")
                if caminho:
                    self.fig_atual.savefig(caminho, dpi=300, bbox_inches='tight')
                    QMessageBox.information(self, "Sucesso", "Diagrama exportado como Imagem com sucesso!")

            elif formato == "dxf":
                caminho, _ = QFileDialog.getSaveFileName(self, "Salvar CAD", "", "Arquivos DXF (*.dxf)")
                if caminho:
                    try:
                        exportar_figura_para_dxf(self.fig_atual, caminho)
                        QMessageBox.information(self, "Sucesso", "Modelo CAD exportado com sucesso!")
                    except Exception as e:
                        QMessageBox.critical(self, "Falha Crítica",
                                             f"Não foi possível processar o DXF: {e}")

    # -------------------------------------------------------------------------
    # Manual do usuário
    # -------------------------------------------------------------------------
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de definição do sistema
        estrutural.

        Navega diretamente para a página 33 do manual (índice 32 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: DEFINIÇÃO DO SISTEMA ESTRUTURAL")
        viewer.display_page(33)  # página 34 → índice 33
        viewer.exec()