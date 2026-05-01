# ============================================================================
# Girder25 - logica_janela_def_sec_transversal.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da janela de definição da seção transversal da via.
# ============================================================================

import os
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QTableWidgetItem, QVBoxLayout,
    QLabel, QFileDialog, QHeaderView, QSpinBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from ui.janela_def_sec_transversal import Ui_janela_def_sec_transversal
from modules.desenho_sec_transversal import desenhar_sec_transversal
from modules.logica_janela_def_superestrutura import DialogoExportacao
from modules.exportar_dxf import exportar_figura_para_dxf
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path


class LogicaDefinirSecaoTransversal(QDialog, Ui_janela_def_sec_transversal):
    """
    Diálogo para configuração da seção transversal da via.
    Gerencia classes normalizadas e modo personalizado, com geração
    de desenho esquemático e exportação.
    """

    # Dimensões padrão para classes normativas (faixa, acostamento, total)
    MAPA_CLASSES = {
        "0":     {"faixa": 375, "acostamento_ext": 300, "acostamento_int": 60, "total": 1190},
        "I - A": {"faixa": 360, "acostamento_ext": 300, "acostamento_int": 60, "total": 1160},
        "I - B": {"faixa": 350, "acostamento": 250,  "total": 1280},
        "II":    {"faixa": 350, "acostamento": 250,  "total": 1280},
        "III":   {"faixa": 350, "acostamento": 150,  "total": 1080},
        "IV":    {"faixa": 300, "acostamento": 150,  "total": 980},
    }

    def __init__(self, gerenciador):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador
        self.fig_atual = None
        self._bloquear_calculo = False

        # Valores persistentes para o modo "Personalizado"
        self._valores_personalizado = {
            "Faixa de rolamento": 350,
            "Acostamento":        250,
            "Acostamento Externo": 250,
            "Acostamento Interno": 250,
        }
        self._spins_personalizado: dict = {}

        # Área de desenho
        self.layout_desenho = QVBoxLayout(self.desenho)
        self.lbl_aguardando = QLabel("Aguardando Geração do Desenho")
        self.lbl_aguardando.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout_desenho.addWidget(self.lbl_aguardando)

        # Configuração dos spinboxes de espessura e inclinação
        self._configurar_spinboxes()

        # Tabela de dimensões
        self.table_dimensoes.setEditTriggers(self.table_dimensoes.EditTrigger.NoEditTriggers)
        self.table_dimensoes.verticalHeader().setVisible(False)
        self.table_dimensoes.horizontalHeader().setVisible(False)

        fonte_tabela = QFont()
        fonte_tabela.setPointSize(12)
        self.table_dimensoes.setFont(fonte_tabela)

        header = self.table_dimensoes.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

        # Conexões dos sinais
        self.radio_simples.toggled.connect(self.configurar_combo_classes)
        self.radio_dupla.toggled.connect(self.configurar_combo_classes)
        self.combo_classe.currentIndexChanged.connect(self.atualizar_tabela)
        self.check_passeio.toggled.connect(self.toggle_passeio)
        self.doubleSpinBox_passeio.valueChanged.connect(self.atualizar_tabela)
        self.spin_inclinacao.valueChanged.connect(self.recalcular_por_inclinacao)
        self.doubleSpinBox_borda.valueChanged.connect(self.recalcular_por_borda)
        self.doubleSpinBox_centro.valueChanged.connect(self.recalcular_por_centro)

        self.atualizar.clicked.connect(self.processar_desenho)
        self.exportar.clicked.connect(self.abrir_dialogo_exportacao)
        self.confirmar.clicked.connect(self.salvar_dados)
        self.cancelar.clicked.connect(self.reject)
        self.manual.clicked.connect(self.abrir_manual)

        # Estado inicial
        self.radio_simples.setChecked(True)
        self.configurar_combo_classes()
        self.toggle_passeio(False)
        self.doubleSpinBox_borda.setValue(8.0)

        # Carrega dados se já existir uma seção salva
        self.carregar_dados_existentes()

    # -------------------------------------------------------------------------
    # Gerenciamento da janela
    # -------------------------------------------------------------------------
    def closeEvent(self, event):
        """Libera a figura do Matplotlib ao fechar o diálogo."""
        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None
        super().closeEvent(event)

    # -------------------------------------------------------------------------
    # Configuração dos controles
    # -------------------------------------------------------------------------
    def _configurar_spinboxes(self):
        """Aplica os intervalos e formatos aos spinboxes de entrada."""
        self.spin_inclinacao.setRange(1.5, 3.0)
        self.spin_inclinacao.setDecimals(1)
        self.spin_inclinacao.setSingleStep(0.1)
        self.spin_inclinacao.setValue(2.0)
        self.spin_inclinacao.setSuffix(" %")

        self.doubleSpinBox_borda.setMinimum(0.0)
        self.doubleSpinBox_borda.setMaximum(1000.0)
        self.doubleSpinBox_borda.setDecimals(1)
        self.doubleSpinBox_borda.setSuffix(" cm")

        self.doubleSpinBox_centro.setMinimum(0.0)
        self.doubleSpinBox_centro.setMaximum(1000.0)
        self.doubleSpinBox_centro.setDecimals(1)
        self.doubleSpinBox_centro.setSuffix(" cm")

        self.doubleSpinBox_passeio.setMinimum(0.0)
        self.doubleSpinBox_passeio.setMaximum(500.0)
        self.doubleSpinBox_passeio.setDecimals(1)
        self.doubleSpinBox_passeio.setSuffix(" cm")

    # -------------------------------------------------------------------------
    # Carregamento de dados preexistentes
    # -------------------------------------------------------------------------
    def carregar_dados_existentes(self):
        """Restaura a interface com os dados de uma seção já definida."""
        obj = self.gerenciador.get_secao_transversal()
        if not obj:
            return

        if obj.classe == "Personalizado":
            dp = getattr(obj, "dimensoes_personalizadas", None)
            if dp:
                self._valores_personalizado["Faixa de rolamento"] = int(dp.get("faixa", 350))
                if dp.get("pista_dupla", False):
                    self.radio_dupla.setChecked(True)
                    self._valores_personalizado["Acostamento Externo"] = int(dp.get("ac_ext", 250))
                    self._valores_personalizado["Acostamento Interno"] = int(dp.get("ac_int", 250))
                else:
                    self.radio_simples.setChecked(True)
                    self._valores_personalizado["Acostamento"] = int(dp.get("ac_ext", 250))
            self.combo_classe.setCurrentText("Personalizado")
        else:
            if obj.classe in ["0", "I - A"]:
                self.radio_dupla.setChecked(True)
            else:
                self.radio_simples.setChecked(True)
            self.combo_classe.setCurrentText(obj.classe)

        self.spin_inclinacao.setValue(float(obj.inclinacao))
        self.doubleSpinBox_borda.setValue(float(obj.h_borda))
        self.doubleSpinBox_centro.setValue(float(obj.h_centro))

        if obj.passeio:
            self.check_passeio.setChecked(True)
            self.doubleSpinBox_passeio.setValue(float(obj.passeio))
        else:
            self.check_passeio.setChecked(False)

        self.processar_desenho()

    # -------------------------------------------------------------------------
    # Combo de classes e toggle de passeio
    # -------------------------------------------------------------------------
    def configurar_combo_classes(self):
        """Preenche a combo com as classes pertinentes ao tipo de pista."""
        self.combo_classe.clear()
        if self.radio_simples.isChecked():
            self.combo_classe.addItems(["I - B", "II", "III", "IV", "Personalizado"])
        else:
            self.combo_classe.addItems(["0", "I - A", "Personalizado"])

    def toggle_passeio(self, estado):
        """Habilita/desabilita o campo de dimensão do passeio."""
        self.doubleSpinBox_passeio.setEnabled(estado)
        if estado:
            self.doubleSpinBox_passeio.setValue(150.0)
        else:
            self.doubleSpinBox_passeio.setValue(0.0)
        self.atualizar_tabela()

    # =========================================================================
    # MODO PERSONALIZADO
    # =========================================================================
    def _salvar_valores_spins_personalizado(self):
        """Armazena os valores correntes de cada QSpinBox personalizado."""
        for label, spin in self._spins_personalizado.items():
            self._valores_personalizado[label] = spin.value()

    def _obter_total_personalizado(self) -> float:
        """Calcula a largura total da seção (sem passeio) para o modo personalizado."""
        dupla = self.radio_dupla.isChecked()
        faixa = self._valores_personalizado.get("Faixa de rolamento", 350)
        if dupla:
            ac_ext = self._valores_personalizado.get("Acostamento Externo", 250)
            ac_int = self._valores_personalizado.get("Acostamento Interno", 250)
            # 2 NJ de 40 cm cada = 80 cm; 2 faixas (uma por sentido)
            return 2 * faixa + ac_ext + ac_int + 80
        else:
            acostamento = self._valores_personalizado.get("Acostamento", 250)
            # 2 acostamentos + 2 faixas + 2 NJ (80 cm)
            return 2 * faixa + 2 * acostamento + 80

    def _obter_total_classe(self) -> float:
        """
        Obtém a largura total (sem passeio) da classe selecionada,
        considerando também o modo personalizado.
        """
        classe = self.combo_classe.currentText()
        if classe == "Personalizado":
            self._salvar_valores_spins_personalizado()
            return self._obter_total_personalizado()
        conf = self.MAPA_CLASSES.get(classe, {})
        return float(conf.get("total", 0))

    def _recalcular_total_personalizado(self):
        """
        Atualiza apenas a célula 'Total' na tabela quando alguma dimensão
        personalizada é alterada.
        """
        self._salvar_valores_spins_personalizado()
        p_val = self.doubleSpinBox_passeio.value() if self.check_passeio.isChecked() else 0.0
        total_real = self._obter_total_personalizado() + 2 * p_val

        for row in range(self.table_dimensoes.rowCount()):
            item = self.table_dimensoes.item(row, 0)
            if item and item.text() == "Total":
                valor_str = (f"{int(total_real)} cm"
                             if total_real == int(total_real)
                             else f"{total_real:.1f} cm")
                total_item = QTableWidgetItem(valor_str)
                total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_dimensoes.setItem(row, 1, total_item)
                break

    def _criar_spin_personalizado(self, label: str) -> QSpinBox:
        """Cria um QSpinBox configurado para uma dimensão editável personalizada."""
        spin = QSpinBox()
        spin.setSuffix(" cm")
        spin.setSingleStep(5)
        if label == "Faixa de rolamento":
            spin.setRange(100, 9999)
            spin.setValue(self._valores_personalizado.get(label, 350))
        else:
            spin.setRange(20, 9999)
            spin.setValue(self._valores_personalizado.get(label, 250))
        spin.valueChanged.connect(self._recalcular_total_personalizado)
        return spin

    def _atualizar_tabela_personalizado(self):
        """
        Reconstrói a tabela de dimensões para o modo personalizado,
        inserindo QSpinBox editáveis.
        """
        self._salvar_valores_spins_personalizado()
        dupla = self.radio_dupla.isChecked()
        p_val = self.doubleSpinBox_passeio.value() if self.check_passeio.isChecked() else 0.0

        if dupla:
            linhas_editaveis = ["Faixa de rolamento", "Acostamento Externo", "Acostamento Interno"]
        else:
            linhas_editaveis = ["Faixa de rolamento", "Acostamento"]

        todas_linhas = list(linhas_editaveis)
        if p_val > 0:
            todas_linhas.append("Passeio")
        todas_linhas.append("Total")

        self.table_dimensoes.setRowCount(len(todas_linhas))
        self.table_dimensoes.setColumnCount(2)
        self._spins_personalizado = {}

        for i, label in enumerate(todas_linhas):
            item_label = QTableWidgetItem(label)
            font = item_label.font()
            font.setBold(True)
            item_label.setFont(font)
            self.table_dimensoes.setItem(i, 0, item_label)

            if label == "Total":
                total_real = self._obter_total_personalizado() + 2 * p_val
                valor_str = (f"{int(total_real)} cm"
                             if total_real == int(total_real)
                             else f"{total_real:.1f} cm")
                self.table_dimensoes.removeCellWidget(i, 1)
                total_item = QTableWidgetItem(valor_str)
                total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_dimensoes.setItem(i, 1, total_item)

            elif label == "Passeio":
                self.table_dimensoes.removeCellWidget(i, 1)
                valor_str = (f"{int(p_val)} cm"
                             if p_val == int(p_val)
                             else f"{p_val:.1f} cm")
                passeio_item = QTableWidgetItem(valor_str)
                passeio_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_dimensoes.setItem(i, 1, passeio_item)

            else:
                spin = self._criar_spin_personalizado(label)
                self._spins_personalizado[label] = spin
                self.table_dimensoes.setCellWidget(i, 1, spin)

        self.table_dimensoes.resizeColumnsToContents()

    def _obter_config_personalizado(self) -> dict:
        """
        Retorna um dicionário normalizado com as dimensões personalizadas atuais.
        """
        self._salvar_valores_spins_personalizado()
        dupla = self.radio_dupla.isChecked()
        faixa = self._valores_personalizado.get("Faixa de rolamento", 350)
        if dupla:
            ac_ext = self._valores_personalizado.get("Acostamento Externo", 250)
            ac_int = self._valores_personalizado.get("Acostamento Interno", 250)
            total = 2 * faixa + ac_ext + ac_int + 80
            return {
                "faixa": faixa, "ac_ext": ac_ext, "ac_int": ac_int,
                "pista_dupla": True, "total": total
            }
        else:
            acostamento = self._valores_personalizado.get("Acostamento", 250)
            total = 2 * faixa + 2 * acostamento + 80
            return {
                "faixa": faixa, "ac_ext": acostamento, "ac_int": 0,
                "pista_dupla": False, "total": total
            }

    # =========================================================================
    # TABELA DE DIMENSÕES
    # =========================================================================
    def atualizar_tabela(self):
        """Atualiza a tabela de dimensões conforme a classe escolhida."""
        classe = self.combo_classe.currentText()
        if not classe:
            return

        if classe == "Personalizado":
            self._atualizar_tabela_personalizado()
            return

        conf = self.MAPA_CLASSES[classe]
        p_val = self.doubleSpinBox_passeio.value() if self.check_passeio.isChecked() else 0.0
        total_real = conf["total"] + (2 * p_val)

        dados_tabela = [("Faixa de rolamento", conf["faixa"])]
        if "acostamento" in conf:
            dados_tabela.append(("Acostamento", conf["acostamento"]))
        else:
            dados_tabela.append(("Acostamento Externo", conf["acostamento_ext"]))
            dados_tabela.append(("Acostamento Interno", conf["acostamento_int"]))

        if p_val > 0:
            dados_tabela.append(("Passeio", p_val))
        dados_tabela.append(("Total", total_real))

        self.table_dimensoes.setRowCount(len(dados_tabela))
        self.table_dimensoes.setColumnCount(2)
        self._spins_personalizado = {}

        for i in range(self.table_dimensoes.rowCount()):
            self.table_dimensoes.removeCellWidget(i, 1)

        for i, (label, valor) in enumerate(dados_tabela):
            item_label = QTableWidgetItem(label)
            font = item_label.font()
            font.setBold(True)
            item_label.setFont(font)
            self.table_dimensoes.setItem(i, 0, item_label)

            if isinstance(valor, float) and valor.is_integer():
                valor_str = f"{int(valor)} cm"
            else:
                valor_str = f"{valor:.1f} cm".replace(".0", "")
            valor_item = QTableWidgetItem(valor_str)
            valor_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_dimensoes.setItem(i, 1, valor_item)

        self.table_dimensoes.resizeColumnsToContents()

    # =========================================================================
    # Recálculo das espessuras (borda ↔ centro)
    # =========================================================================
    def recalcular_por_inclinacao(self):
        self.recalcular_por_borda()

    def recalcular_por_borda(self):
        """Recalcula a espessura no centro a partir da borda e da inclinação."""
        if self._bloquear_calculo:
            return
        try:
            self._bloquear_calculo = True
            h_b = self.doubleSpinBox_borda.value()
            inc = self.spin_inclinacao.value() / 100.0
            total = self._obter_total_classe()
            larg_pav = total - 80  # desconta as duas barreiras NJ
            h_c = h_b + (larg_pav / 2) * inc
            self.doubleSpinBox_centro.setValue(h_c)
        except Exception:
            pass
        finally:
            self._bloquear_calculo = False

    def recalcular_por_centro(self):
        """Recalcula a espessura na borda a partir do centro e da inclinação."""
        if self._bloquear_calculo:
            return
        try:
            self._bloquear_calculo = True
            h_c = self.doubleSpinBox_centro.value()
            inc = self.spin_inclinacao.value() / 100.0
            total = self._obter_total_classe()
            larg_pav = total - 80
            h_b = h_c - (larg_pav / 2) * inc
            self.doubleSpinBox_borda.setValue(h_b)
        except Exception:
            pass
        finally:
            self._bloquear_calculo = False

    # =========================================================================
    # VALIDAÇÃO
    # =========================================================================
    def validar(self):
        """Verifica consistência dos dados e retorna dicionário com os valores."""
        try:
            h_b = self.doubleSpinBox_borda.value()
            if h_b < 7:
                QMessageBox.critical(self, "Erro",
                                     "A espessura do pavimento deve ser no mínimo 7 cm.")
                return None

            p_val = False
            if self.check_passeio.isChecked():
                p_val = self.doubleSpinBox_passeio.value()
                if p_val <= 0:
                    QMessageBox.critical(self, "Erro",
                                         "A dimensão do passeio deve ser um número maior que 0.")
                    return None

            inclinacao_percent = self.spin_inclinacao.value()
            classe = self.combo_classe.currentText()

            dimensoes_personalizadas = None
            if classe == "Personalizado":
                dimensoes_personalizadas = self._obter_config_personalizado()

            return {
                "classe": classe,
                "h_borda": h_b,
                "h_centro": self.doubleSpinBox_centro.value(),
                "inclinacao": inclinacao_percent,
                "passeio": p_val,
                "dimensoes_personalizadas": dimensoes_personalizadas,
            }
        except ValueError:
            QMessageBox.critical(self, "Erro", "Valores numéricos inválidos.")
            return None

    # =========================================================================
    # DESENHO E EXPORTAÇÃO
    # =========================================================================
    def processar_desenho(self):
        """Gera o diagrama da seção transversal com base nos dados atuais."""
        v = self.validar()
        if not v:
            return

        if self.fig_atual:
            plt.close(self.fig_atual)
            self.fig_atual = None
        for i in reversed(range(self.layout_desenho.count())):
            widget = self.layout_desenho.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        try:
            config_pers = None
            if v["classe"] == "Personalizado":
                config_pers = v["dimensoes_personalizadas"]

            self.fig_atual = desenhar_sec_transversal(
                v["classe"], v["h_borda"], v["h_centro"], v["passeio"],
                config_personalizado=config_pers
            )
            if self.fig_atual:
                self.layout_desenho.addWidget(FigureCanvas(self.fig_atual))
                self.exportar.setEnabled(True)
            else:
                lbl = QLabel("Pré-visualização não disponível para esta configuração.")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.layout_desenho.addWidget(lbl)
        except Exception as e:
            lbl = QLabel(f"Erro ao gerar desenho:\n{str(e)}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout_desenho.addWidget(lbl)

    def abrir_dialogo_exportacao(self):
        """Exporta o diagrama em PNG ou DXF."""
        if not self.fig_atual:
            return
        dlg = DialogoExportacao(self)
        if dlg.exec():
            formato = dlg.formato_escolhido
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar", "", f"{formato.upper()} (*.{formato})")
            if caminho:
                if formato == "png":
                    self.fig_atual.savefig(caminho, dpi=300)
                else:
                    exportar_figura_para_dxf(self.fig_atual, caminho)
                QMessageBox.information(self, "Sucesso", "Exportado!")

    # =========================================================================
    # PERSISTÊNCIA
    # =========================================================================
    def salvar_dados(self):
        """Valida e salva a seção transversal no gerenciador de dados."""
        v = self.validar()
        if v:
            self.gerenciador.definir_secao_transversal(
                v["classe"],
                v["h_borda"],
                v["h_centro"],
                v["inclinacao"],
                v["passeio"],
                v["dimensoes_personalizadas"],
            )
            self.accept()

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção da seção transversal da via.

        Navega diretamente para a página 36 do manual (índice 35 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: SEÇÃO TRANSVERSAL DA VIA")
        viewer.display_page(36)  # página 35 → índice 36
        viewer.exec()