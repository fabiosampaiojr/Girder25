# ============================================================================
# Girder25 - logica_janela_sec_super.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da janela de definição da seção transversal da superestrutura.
# ============================================================================

import os
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QVBoxLayout, QLabel, QFileDialog, QComboBox, QPushButton
)
from PyQt6.QtCore import Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.janela_sec_super import Ui_janela_sec_super
from modules.logica_janela_def_superestrutura import DialogoExportacao
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path

from modules.funcoes_sec_super import (
    calcular_secao, calcular_secao_reversa, desenhar_secao,
    desenhar_sec_transversal_completa, gerar_memorial_propriedades_secao
)
from modules.gerar_html import gerar_html_propriedades_secao
from modules.logica_janela_memorial import LogicaJanelaMemorial


class DialogoEscolhaExportacao(QDialog):
    """Diálogo para o usuário escolher qual desenho deseja exportar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escolher Desenho para Exportar")
        self.setFixedSize(300, 150)
        self.layout = QVBoxLayout(self)

        self.label = QLabel("Qual desenho deseja exportar?")
        self.combo = QComboBox()
        self.combo.addItems([
            "Pré-visualização da Seção Transversal",
            "Pré-visualização da Longarina"
        ])

        self.btn_ok = QPushButton("Continuar")
        self.btn_ok.clicked.connect(self.accept)

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.combo)
        self.layout.addWidget(self.btn_ok)


class LogicaDefinirSecaoSuperestrutura(QDialog, Ui_janela_sec_super):
    """
    Controlador da janela de definição da seção transversal da superestrutura.
    Permite configurar a geometria das longarinas (retangular, T, I ou
    personalizada), calcular propriedades e visualizar os desenhos.
    """

    MAPA_CLASSES = {
        "0":     {"faixa": 375, "ac_ext": 300, "ac_int": 60,  "pista_dupla": True},
        "I - A": {"faixa": 360, "ac_ext": 300, "ac_int": 60,  "pista_dupla": True},
        "I - B": {"faixa": 350, "ac_ext": 250, "ac_int": 0,   "pista_dupla": False},
        "II":    {"faixa": 350, "ac_ext": 250, "ac_int": 0,   "pista_dupla": False},
        "III":   {"faixa": 350, "ac_ext": 150, "ac_int": 0,   "pista_dupla": False},
        "IV":    {"faixa": 300, "ac_ext": 150, "ac_int": 0,   "pista_dupla": False},
    }

    MAPA_TIPO_COMBO = {
        "Seção Retângular": "Retangular",
        'Seção "T"': "T",
        'Seção "I"': "I",
        "Seção Personalizada": "Personalizada"
    }

    def __init__(self, gerenciador):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador
        self.fig_atual = None
        self.fig_longarina = None
        self.largura_total = 0.0
        self.dados = {}
        self.parametros_geometricos = {}
        self.largura_colaborante = None

        # Área de desenho principal (seção transversal completa)
        self.layout_desenho = QVBoxLayout(self.desenho)
        self.lbl_aguardando = QLabel("Aguardando Geração do Desenho")
        self.lbl_aguardando.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_desenho.addWidget(self.lbl_aguardando)

        # Área de desenho secundário (longarina isolada)
        self.layout_desenho_2 = QVBoxLayout(self.desenho_2)
        self.lbl_aguardando_2 = QLabel("Aguardando Geração da Longarina")
        self.lbl_aguardando_2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_desenho_2.addWidget(self.lbl_aguardando_2)

        self.configurar_spinboxes()
        self.calcular_largura_total_da_via()

        # Conexões de sinais
        self.spin_n_longarina.valueChanged.connect(self.atualizar_labels_geometria)
        self.spin_d_extremidade.valueChanged.connect(self.atualizar_labels_geometria)

        self.combo_tipo.currentTextChanged.connect(self.atualizar_pagina_stacked_widget)
        self.atualizar_e_calcular.clicked.connect(self.atualizar_calculos_e_desenho_longarina)

        self.radio_cm.toggled.connect(self.atualizar_html_propriedades)
        self.radio_m.toggled.connect(self.atualizar_html_propriedades)

        self.atualizar.clicked.connect(self.processar_desenho)
        self.exportar.clicked.connect(self.abrir_dialogo_exportacao)
        self.confirmar.clicked.connect(self.salvar_dados)
        self.cancelar.clicked.connect(self.reject)

        if hasattr(self, 'memorial'):
            self.memorial.clicked.connect(self.abrir_memorial_propriedades)

        # Controle de largura colaborante
        self.check_largura_colaborante.toggled.connect(self.toggle_largura_colaborante)
        self.spin_largura_colaborante.valueChanged.connect(self.atualizar_largura_colaborante)

        # Manual do usuário
        self.manual.clicked.connect(self.abrir_manual)

        self.exportar.setEnabled(False)
        self.atualizar_labels_geometria()
        self.radio_cm.setChecked(True)

        # Inicialização da interface
        self.atualizar_pagina_stacked_widget(self.combo_tipo.currentText())
        self.carregar_dados_existentes()

    # -------------------------------------------------------------------------
    # Gerenciamento da janela
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        """Libera todas as figuras do Matplotlib ao fechar o diálogo."""
        for fig in (self.fig_atual, self.fig_longarina):
            if fig:
                plt.close(fig)
        self.fig_atual = None
        self.fig_longarina = None
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Configuração dos controles
    # -------------------------------------------------------------------------
    def configurar_spinboxes(self):
        """Aplica limites, passos e sufixos a todos os spinboxes da janela."""
        self.spin_n_longarina.setRange(1, 20)
        self.spin_n_longarina.setValue(2)

        self.spin_h_laje.setRange(15, 50)
        self.spin_h_laje.setSingleStep(5)
        self.spin_h_laje.setValue(25)
        self.spin_h_laje.setSuffix(" cm")

        self.spin_d_extremidade.setRange(50, 300)
        self.spin_d_extremidade.setSingleStep(5)
        self.spin_d_extremidade.setValue(80)
        self.spin_d_extremidade.setSuffix(" cm")

        self.check_largura_colaborante.setChecked(False)
        self.spin_largura_colaborante.setRange(50, 250)
        self.spin_largura_colaborante.setSingleStep(5)
        self.spin_largura_colaborante.setValue(120)
        self.spin_largura_colaborante.setSuffix(" cm")
        self.spin_largura_colaborante.setEnabled(False)

        # Tipo Retangular
        self.ret_bw.setRange(20, 100)
        self.ret_bw.setValue(30)
        self.ret_bw.setSuffix(" cm")
        self.ret_h.setRange(40, 200)
        self.ret_h.setValue(80)
        self.ret_h.setSuffix(" cm")

        # Tipo T
        self.t_bw.setRange(20, 60)
        self.t_bw.setValue(25)
        self.t_bw.setSuffix(" cm")
        self.t_h.setRange(60, 250)
        self.t_h.setValue(120)
        self.t_h.setSuffix(" cm")
        self.t_bf.setRange(60, 400)
        self.t_bf.setValue(200)
        self.t_bf.setSuffix(" cm")
        self.t_hf.setRange(10, 25)
        self.t_hf.setValue(15)
        self.t_hf.setSuffix(" cm")

        # Tipo I
        self.i_bw.setRange(12, 40)
        self.i_bw.setValue(20)
        self.i_bw.setSuffix(" cm")
        self.i_h.setRange(60, 250)
        self.i_h.setValue(120)
        self.i_h.setSuffix(" cm")
        self.i_bft.setRange(30, 120)
        self.i_bft.setValue(60)
        self.i_bft.setSuffix(" cm")
        self.i_hft.setRange(8, 30)
        self.i_hft.setValue(12)
        self.i_hft.setSuffix(" cm")
        self.i_bfb.setRange(30, 120)
        self.i_bfb.setValue(50)
        self.i_bfb.setSuffix(" cm")
        self.i_hfb.setRange(10, 30)
        self.i_hfb.setValue(15)
        self.i_hfb.setSuffix(" cm")

        # Tipo Personalizada
        self.personalizado_a.setRange(500, 20000)
        self.personalizado_a.setSingleStep(100)
        self.personalizado_a.setValue(3000)
        self.personalizado_a.setSuffix(" cm²")

        self.personalizado_ix.setRange(10000, 100000000)
        self.personalizado_ix.setSingleStep(10000)
        self.personalizado_ix.setValue(1000000)
        self.personalizado_ix.setSuffix(" cm⁴")

        self.personalizado_h.setRange(30, 300)
        self.personalizado_h.setValue(80)
        self.personalizado_h.setSuffix(" cm")

        self.check_exibir_via.setChecked(True)

    # -------------------------------------------------------------------------
    # Largura colaborante
    # -------------------------------------------------------------------------
    def toggle_largura_colaborante(self, checked: bool):
        """Habilita/desabilita o campo de largura colaborante."""
        if checked:
            self.spin_largura_colaborante.setEnabled(True)
            self.spin_largura_colaborante.setValue(120)
            self.largura_colaborante = float(self.spin_largura_colaborante.value())
        else:
            self.spin_largura_colaborante.setEnabled(False)
            self.largura_colaborante = None
        self.atualizar_calculos_e_desenho_longarina()

    def atualizar_largura_colaborante(self, valor: int):
        """Atualiza a largura colaborante quando o usuário altera o spinbox."""
        if self.check_largura_colaborante.isChecked():
            self.largura_colaborante = float(valor)
            self.atualizar_calculos_e_desenho_longarina()

    # -------------------------------------------------------------------------
    # Alternância entre tipos de seção
    # -------------------------------------------------------------------------
    def atualizar_pagina_stacked_widget(self, tipo_selecionado):
        """Alterna a página do QStackedWidget conforme o tipo de seção escolhido."""
        if tipo_selecionado == "Seção Retângular":
            self.stackedWidget.setCurrentWidget(self.page_retangular)
        elif tipo_selecionado == 'Seção "T"':
            self.stackedWidget.setCurrentWidget(self.page_t)
        elif tipo_selecionado == 'Seção "I"':
            self.stackedWidget.setCurrentWidget(self.page_i)
        elif tipo_selecionado == "Seção Personalizada":
            self.stackedWidget.setCurrentWidget(self.page_personalizada)

        self.atualizar_calculos_e_desenho_longarina()

    # -------------------------------------------------------------------------
    # Obtenção dos dados da seção ativa
    # -------------------------------------------------------------------------
    def obter_dados_secao(self) -> dict:
        """Monta e retorna o dicionário de dados conforme o tipo de seção ativo."""
        tipo = self.combo_tipo.currentText()

        if tipo == "Seção Retângular":
            return {
                "Tipo": "Retangular",
                "bw": float(self.ret_bw.value()),
                "h": float(self.ret_h.value())
            }
        elif tipo == 'Seção "T"':
            return {
                "Tipo": "T",
                "bw": float(self.t_bw.value()),
                "h": float(self.t_h.value()),
                "bf": float(self.t_bf.value()),
                "hf": float(self.t_hf.value())
            }
        elif tipo == 'Seção "I"':
            return {
                "Tipo": "I",
                "bw": float(self.i_bw.value()),
                "h": float(self.i_h.value()),
                "btf": float(self.i_bft.value()),
                "hft": float(self.i_hft.value()),
                "bfb": float(self.i_bfb.value()),
                "hfb": float(self.i_hfb.value())
            }
        elif tipo == "Seção Personalizada":
            ix = float(self.personalizado_ix.value())
            h = float(self.personalizado_h.value())
            return calcular_secao_reversa(h_total=h, i_x=ix)

        return {}

    # -------------------------------------------------------------------------
    # Cálculo e desenho da longarina
    # -------------------------------------------------------------------------
    def atualizar_calculos_e_desenho_longarina(self):
        """
        Obtém os dados da seção, calcula as propriedades geométricas,
        atualiza o HTML e redesenha a longarina isolada.
        """
        self.dados = self.obter_dados_secao()
        if not self.dados:
            return

        tipo = self.combo_tipo.currentText()
        h_laje = float(self.spin_h_laje.value())

        if tipo == "Seção Personalizada":
            h        = float(self.personalizado_h.value())
            area_long = float(self.personalizado_a.value())
            ix_long  = float(self.personalizado_ix.value())
            ycg_long = h / 2.0

            if self.largura_colaborante is not None:
                lc     = self.largura_colaborante
                a_laje = lc * h_laje
                y_laje = h + h_laje / 2
                area_total = area_long + a_laje
                ycg_comp   = (area_long * ycg_long + a_laje * y_laje) / area_total
                i_laje_prop = (lc * h_laje**3) / 12
                ix_total = (
                    ix_long + area_long * (ycg_long - ycg_comp)**2
                    + i_laje_prop + a_laje * (y_laje - ycg_comp)**2
                )
                self.parametros_geometricos = {
                    "Area": area_total,
                    "Area Longarina": area_long,
                    "Ix": ix_total,
                    "h": h + h_laje,
                    "ycg": ycg_comp
                }
            else:
                self.parametros_geometricos = {
                    "Area": area_long,
                    "Area Longarina": area_long,
                    "Ix": ix_long,
                    "h": h,
                    "ycg": ycg_long
                }
        else:
            self.parametros_geometricos = calcular_secao(
                self.dados,
                h_laje=h_laje,
                largura_colaborante=self.largura_colaborante
            )

        self.atualizar_html_propriedades()

        # Redesenha a longarina isolada
        if self.fig_longarina:
            plt.close(self.fig_longarina)
            self.fig_longarina = None

        for i in reversed(range(self.layout_desenho_2.count())):
            widget = self.layout_desenho_2.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        self.fig_longarina = desenhar_secao(
            self.dados,
            exibir_cotas=True,
            h_laje=h_laje,
            largura_colaborante=self.largura_colaborante
        )
        self.layout_desenho_2.addWidget(FigureCanvas(self.fig_longarina))

    # -------------------------------------------------------------------------
    # Exibição das propriedades
    # -------------------------------------------------------------------------
    def atualizar_html_propriedades(self):
        """
        Atualiza o painel HTML de propriedades geométricas conforme a
        unidade selecionada (cm ou m).
        """
        if not self.parametros_geometricos:
            return
        unidade = "cm" if self.radio_cm.isChecked() else "m"
        html = gerar_html_propriedades_secao(self.parametros_geometricos, unidade=unidade)
        self.html_propriedades_secao.setText(html)

    def abrir_memorial_propriedades(self):
        """Exibe o memorial de cálculo das propriedades da seção."""
        if not self.dados or not self.parametros_geometricos:
            QMessageBox.warning(self, "Aviso",
                                "Calcule as propriedades da seção primeiro para gerar o memorial.")
            return

        is_pers = (self.combo_tipo.currentText() == "Seção Personalizada")
        h_laje = float(self.spin_h_laje.value())

        dados_pers = None
        if is_pers:
            dados_pers = {
                "Area": float(self.personalizado_a.value()),
                "Ix": float(self.personalizado_ix.value()),
                "h": float(self.personalizado_h.value())
            }

        html = gerar_memorial_propriedades_secao(
            dados=self.dados,
            is_personalizada=is_pers,
            h_laje=h_laje,
            largura_colaborante=self.largura_colaborante,
            dados_pers=dados_pers
        )

        dlg = LogicaJanelaMemorial("Memorial de Cálculo — Propriedades da Seção", html, self)
        dlg.exec()

    # -------------------------------------------------------------------------
    # Carregamento de dados existentes
    # -------------------------------------------------------------------------
    def carregar_dados_existentes(self):
        """
        Restaura todos os campos da janela com base no objeto
        SecaoTransversalSuperestrutura já salvo no gerenciador.
        """
        obj = self.gerenciador.get_secao_superestrutura()
        if not obj:
            return

        # Dados básicos
        self.spin_n_longarina.setValue(obj.n_longarinas)
        self.spin_h_laje.setValue(int(obj.h_laje))
        self.spin_d_extremidade.setValue(int(obj.d_extremidade))

        # Largura colaborante
        if obj.largura_colaborante is not None:
            self.check_largura_colaborante.setChecked(True)
            self.spin_largura_colaborante.setValue(int(obj.largura_colaborante))
            self.largura_colaborante = obj.largura_colaborante
        else:
            self.check_largura_colaborante.setChecked(False)
            self.largura_colaborante = None

        # Geometria da seção
        dados_secao = obj.dados
        parametros = obj.parametros_geometricos

        self.dados = dados_secao.copy()
        self.parametros_geometricos = parametros.copy()

        tipo_interno = dados_secao.get("Tipo", "Retangular")

        # Seleciona o tipo correto no combo
        for texto_combo, tipo_map in self.MAPA_TIPO_COMBO.items():
            if tipo_map == tipo_interno:
                self.combo_tipo.setCurrentText(texto_combo)
                break

        # Preenche os spinboxes conforme o tipo
        if tipo_interno == "Retangular":
            if self.combo_tipo.currentText() == "Seção Personalizada":
                self.personalizado_a.setValue(parametros["Area Longarina"])
                self.personalizado_ix.setValue(parametros["Ix"])
                self.personalizado_h.setValue(int(parametros["h"]))
            else:
                self.ret_bw.setValue(int(dados_secao.get("bw", 30)))
                self.ret_h.setValue(int(dados_secao.get("h", 80)))

        elif tipo_interno == "T":
            self.t_bw.setValue(int(dados_secao.get("bw", 25)))
            self.t_h.setValue(int(dados_secao.get("h", 120)))
            self.t_bf.setValue(int(dados_secao.get("bf", 200)))
            self.t_hf.setValue(int(dados_secao.get("hf", 15)))

        elif tipo_interno == "I":
            self.i_bw.setValue(int(dados_secao.get("bw", 20)))
            self.i_h.setValue(int(dados_secao.get("h", 120)))
            self.i_bft.setValue(int(dados_secao.get("btf", 60)))
            self.i_hft.setValue(int(dados_secao.get("hft", 12)))
            self.i_bfb.setValue(int(dados_secao.get("bfb", 50)))
            self.i_hfb.setValue(int(dados_secao.get("hfb", 15)))

        # Atualiza a página do stacked widget
        self.atualizar_pagina_stacked_widget(self.combo_tipo.currentText())

        # Atualiza labels, HTML e desenhos
        self.atualizar_labels_geometria()
        self.atualizar_html_propriedades()
        self.atualizar_calculos_e_desenho_longarina()
        self.processar_desenho()

    # -------------------------------------------------------------------------
    # Auxiliares de formatação e geometria da via
    # -------------------------------------------------------------------------
    def formatar_numero(self, valor):
        """Formata um número com até 3 casas decimais, removendo zeros inúteis."""
        v_arredondado = round(valor, 3)
        if v_arredondado == int(v_arredondado):
            return str(int(v_arredondado))
        return str(v_arredondado)

    def calcular_largura_total_da_via(self):
        """
        Calcula a largura total da via com base na seção transversal definida
        anteriormente (necessária como pré-requisito).
        """
        sec = self.gerenciador.get_secao_transversal()
        if not sec:
            QMessageBox.warning(self, "Aviso",
                                "É necessário definir a Seção Transversal primeiro!")
            return

        config = sec.obter_config_via()
        if not config:
            return

        f   = config["faixa"]
        ae  = config["ac_ext"]
        ai  = config["ac_int"]
        dupla = config["pista_dupla"]
        p   = sec.passeio if sec.passeio else 0
        l_nj = 40

        x_face_externa_nj_esq  = p
        x_face_interna_nj_esq  = x_face_externa_nj_esq + l_nj

        if dupla:
            dist_miolo = ai + 2 * f + ae
        else:
            dist_miolo = 2 * ae + 2 * f

        x_face_interna_nj_dir  = x_face_interna_nj_esq + dist_miolo
        x_face_externa_nj_dir  = x_face_interna_nj_dir + l_nj

        self.largura_total = x_face_externa_nj_dir + (p if (p > 0 and not dupla) else 0)

    def atualizar_labels_geometria(self):
        """
        Atualiza os labels que exibem a largura total da via e a distância
        entre eixos das longarinas.
        """
        n_longarinas = self.spin_n_longarina.value()
        d_extremidade = float(self.spin_d_extremidade.value())

        if n_longarinas > 1:
            d_entre_eixos = (self.largura_total - 2 * d_extremidade) / (n_longarinas - 1)
        else:
            d_entre_eixos = 0.0

        self.label_largura_total.setText(
            f"Largura Total: {self.formatar_numero(self.largura_total)} cm.")
        self.label_d_entre_eixos.setText(
            f"Distância entre eixos: {self.formatar_numero(d_entre_eixos)} cm.")

    # -------------------------------------------------------------------------
    # Desenho e exportação
    # -------------------------------------------------------------------------
    def processar_desenho(self):
        """Gera o desenho completo da seção transversal com as longarinas."""
        sec = self.gerenciador.get_secao_transversal()
        if not sec:
            QMessageBox.warning(self, "Aviso",
                                "A Seção Transversal deve ser definida antes de gerar o desenho.")
            return

        if not self.dados:
            QMessageBox.warning(self, "Aviso",
                                "Atualize e calcule as propriedades da longarina primeiro.")
            return

        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None

        for i in reversed(range(self.layout_desenho.count())):
            widget = self.layout_desenho.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        area_longarina = self.parametros_geometricos.get("Area Longarina", 0.0)

        # Dados da classe personalizada, se aplicável
        config_pers = None
        if sec.classe == "Personalizado":
            config_pers = sec.obter_config_via()

        self.fig_atual = desenhar_sec_transversal_completa(
            classe=sec.classe,
            h_borda=sec.h_borda,
            h_centro=sec.h_centro,
            n_longarinas=self.spin_n_longarina.value(),
            h_laje=float(self.spin_h_laje.value()),
            d_extremidade=float(self.spin_d_extremidade.value()),
            dados=self.dados,
            area_longarina=area_longarina,
            passeio=sec.passeio,
            exibir_via=self.check_exibir_via.isChecked(),
            config_personalizado=config_pers
        )

        if self.fig_atual is None:
            QMessageBox.warning(self, "Aviso",
                                "Não foi possível gerar o desenho para a classe Personalizado.\n"
                                "Verifique se as dimensões personalizadas foram definidas.")
            self.exportar.setEnabled(False)
            return

        self.layout_desenho.addWidget(FigureCanvas(self.fig_atual))
        self.exportar.setEnabled(True)

    def abrir_dialogo_exportacao(self):
        """Oferece exportação do desenho selecionado (via ou longarina)."""
        if not self.fig_atual and not self.fig_longarina:
            return

        dlg_escolha = DialogoEscolhaExportacao(self)
        if dlg_escolha.exec():
            index_escolha = dlg_escolha.combo.currentIndex()
            figura_alvo = self.fig_atual if index_escolha == 0 else self.fig_longarina

            if not figura_alvo:
                QMessageBox.warning(self, "Aviso",
                                    "O desenho selecionado ainda não foi gerado.")
                return

            dlg = DialogoExportacao(self)
            if dlg.exec():
                formato = dlg.formato_escolhido
                caminho, _ = QFileDialog.getSaveFileName(
                    self, "Salvar", "", f"{formato.upper()} (*.{formato})")
                if caminho:
                    if formato == "png":
                        figura_alvo.savefig(caminho, dpi=300)
                    else:
                        exportar_figura_para_dxf(figura_alvo, caminho)
                    QMessageBox.information(self, "Sucesso", "Desenho exportado com sucesso!")

    # -------------------------------------------------------------------------
    # Salvamento dos dados
    # -------------------------------------------------------------------------
    def salvar_dados(self):
        """Persiste a definição da seção da superestrutura no gerenciador."""
        if not self.dados or not self.parametros_geometricos:
            QMessageBox.warning(self, "Aviso",
                                "Calcule as propriedades da seção antes de confirmar.")
            return

        self.gerenciador.definir_secao_superestrutura(
            n_longarinas=self.spin_n_longarina.value(),
            h_laje=float(self.spin_h_laje.value()),
            d_extremidade=float(self.spin_d_extremidade.value()),
            largura_total=self.largura_total,
            dados=self.dados,
            parametros_geometricos=self.parametros_geometricos,
            largura_colaborante=self.largura_colaborante
        )
        self.accept()

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de definição da seção
        transversal da superestrutura.

        Navega diretamente para a página 40 do manual (índice 39 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: DEFINIÇÃO DA SEÇÃO TRANSVERSAL DA SUPERESTRUTURA")
        viewer.display_page(39)  # página 40 do manual → índice 39
        viewer.exec()