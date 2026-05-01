# ============================================================================
# Girder25 - logica_principal.py
# Autor: Fábio Henrique Sampaio Júnior
# Controlador da Janela Principal
# ============================================================================
import os

from PyQt6.QtWidgets import QMainWindow, QMessageBox
from PyQt6.QtGui import QCloseEvent
from ui.janela_principal import Ui_Janela_Principal

from modules.logica_janela_def_superestrutura import LogicaDefinirSuperestrutura
from modules.logica_janela_def_sec_transversal import LogicaDefinirSecaoTransversal
from modules.logica_janela_sec_super import LogicaDefinirSecaoSuperestrutura
from modules.logica_janela_coef_impacto import LogicaJanelaCoefImpacto
from modules.logica_selecao_trem_tipo import LogicaSelecaoTremTipo
from modules.logica_janela_peso_proprio import LogicaJanelaPesoProprio
from modules.logica_janela_sobrecarga import LogicaJanelaSobrecarga
from modules.logica_janela_temperatura import LogicaJanelaTemperatura
from modules.logica_janela_carga_movel import LogicaJanelaCargaMovel
from modules.logica_janela_esforcos_calculo import LogicaJanelaEsforcosCalculo
from modules.logica_janela_armadura_longitudinal import LogicaJanelaArmaduraLongitudinal
from modules.logica_janela_armadura_transversal import LogicaJanelaArmaduraTransversal
from modules.visualizador_pdf import PDFViewer
from modules.utils import resource_path  # Necessário para localizar o manual

from modules.html_janela_inicial import (
    get_html_status_sistema,
    get_html_status_secao,
    get_html_status_superestrutura,
    get_html_status_coef_impacto,
    get_html_trem_tipo,
    get_html_esforcos_permanentes,
    get_html_status_temperatura,
    get_html_status_carga_movel,
    get_html_status_esforcos_calculo,
    get_html_status_armadura,
)

from modules.logica_arquivo import LogicaArquivo

# Tipos estruturais considerados hiperestáticos (habilitam o cálculo de temperatura)
_TIPOS_HIPERESTATICOS = {
    "Hiperestática: Vão Contínuo sem Balanço",
    "Hiperestática: Vão Contínuo com Balanço",
}


class LogicaPrincipal(QMainWindow, Ui_Janela_Principal):
    """
    Controlador da janela principal do Girder25.
    Gerencia a abertura de todas as janelas de definição e cálculo,
    habilita/desabilita botões conforme o progresso e mantém a interface
    atualizada com status em HTML.
    """

    def __init__(self, gerenciador_dados):
        super().__init__()
        self.setupUi(self)
        self.gerenciador = gerenciador_dados

        # =====================================================================
        # Gerenciador de arquivos (novo, abrir, salvar)
        # =====================================================================
        self.arquivo_controller = LogicaArquivo(self, self.gerenciador)
        self.arquivo_controller._atualizar_titulo_janela()

        # =====================================================================
        # Conexões dos botões da barra lateral
        # =====================================================================
        self.definir_super_estrutura.clicked.connect(self.abrir_definicao_superestrutura)
        self.definir_sec_transversal.clicked.connect(self.abrir_definicao_secao_transversal)
        self.definir_geometria_super.clicked.connect(self.abrir_definicao_geometria_super)
        self.coef_impacto.clicked.connect(self.abrir_janela_coef_impacto)
        self.trem_tipo_longarina.clicked.connect(self.abrir_selecao_trem_tipo)
        self.peso_proprio.clicked.connect(self.abrir_janela_peso_proprio)
        self.sobre_carga.clicked.connect(self.abrir_janela_sobrecarga)
        self.temperatura.clicked.connect(self.abrir_janela_temperatura)
        self.carga_movel.clicked.connect(self.abrir_janela_carga_movel)
        self.esforcos_calculo.clicked.connect(self.abrir_janela_esforcos_calculo)

        if hasattr(self, 'armadura_longitudinal'):
            self.armadura_longitudinal.clicked.connect(self.abrir_janela_armadura_longitudinal)
        if hasattr(self, 'armadura_transversal'):
            self.armadura_transversal.clicked.connect(self.abrir_janela_armadura_transversal)

        # Botão de acesso ao manual
        self.manual.clicked.connect(self.abrir_manual)

        # =====================================================================
        # Menu Arquivo
        # =====================================================================
        self.actionNovo.triggered.connect(self.arquivo_controller.novo_arquivo)
        self.actionAbrir.triggered.connect(self.arquivo_controller.abrir_arquivo)
        self.actionSalvar.triggered.connect(self.arquivo_controller.salvar_arquivo)
        self.actionSalvar_Como.triggered.connect(self.arquivo_controller.salvar_arquivo_como)

        self.atualizar_interface()

    # =========================================================================
    # Gerenciamento do fechamento da janela
    # =========================================================================
    def closeEvent(self, event: QCloseEvent):
        """
        Intercepta o evento de fechamento para verificar se há alterações
        não salvas, oferecendo ao usuário a possibilidade de salvar,
        descartar ou cancelar.
        """
        if self.arquivo_controller.verificar_salvamento_pendente():
            event.accept()
        else:
            event.ignore()

    # =========================================================================
    # Verificação de dependências
    # =========================================================================
    def checar_aviso_edicao(self, tem_objeto, mensagem):
        """
        Exibe um diálogo de confirmação quando o usuário tenta redefinir
        uma etapa já concluída. A alteração descarta todos os cálculos
        posteriores que dependem dela.
        """
        if tem_objeto:
            resposta = QMessageBox.question(
                self, "Aviso de Alteração",
                f"Você já definiu isso anteriormente. Alterar {mensagem} apagará os "
                f"cálculos e resultados que dependem dele.\n\nDeseja continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            return resposta == QMessageBox.StandardButton.Yes
        return True

    # =========================================================================
    # Abertura das janelas de definição e cálculo
    # =========================================================================

    def abrir_definicao_superestrutura(self):
        tem_sup = self.gerenciador.get_superestrutura() is not None
        if not self.checar_aviso_edicao(tem_sup, "o Sistema Estrutural"):
            return

        dialog = LogicaDefinirSuperestrutura(self.gerenciador)
        if dialog.exec():
            self.gerenciador.coeficientes_impacto = None
            self.gerenciador.esforcos.clear()
            self.gerenciador.esforcos_calculo = None
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_definicao_secao_transversal(self):
        tem_sec = self.gerenciador.get_secao_transversal() is not None
        if not self.checar_aviso_edicao(tem_sec, "a Seção Transversal"):
            return

        dialog = LogicaDefinirSecaoTransversal(self.gerenciador)
        if dialog.exec():
            self.gerenciador.secao_superestrutura = None
            self.gerenciador.trem_tipo_longarina = None
            self.gerenciador.coeficientes_impacto = None
            self.gerenciador.esforcos.clear()
            self.gerenciador.esforcos_calculo = None
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_definicao_geometria_super(self):
        tem_geo = self.gerenciador.get_secao_superestrutura() is not None
        if not self.checar_aviso_edicao(tem_geo, "a Geometria da Superestrutura"):
            return

        dialog = LogicaDefinirSecaoSuperestrutura(self.gerenciador)
        if dialog.exec():
            self.gerenciador.trem_tipo_longarina = None
            self.gerenciador.esforcos.clear()
            self.gerenciador.esforcos_calculo = None
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_janela_coef_impacto(self):
        tem_coef = self.gerenciador.get_coeficientes_impacto() is not None
        if not self.checar_aviso_edicao(tem_coef, "os Coeficientes de Impacto"):
            return

        dialog = LogicaJanelaCoefImpacto(self.gerenciador)
        if dialog.exec():
            if "carga_movel" in self.gerenciador.esforcos:
                del self.gerenciador.esforcos["carga_movel"]
            self.gerenciador.esforcos_calculo = None
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_selecao_trem_tipo(self):
        tem_trem = self.gerenciador.get_trem_tipo_longarina() is not None
        if not self.checar_aviso_edicao(tem_trem, "o Trem Tipo"):
            return

        dialog = LogicaSelecaoTremTipo(self.gerenciador)
        if dialog.exec():
            if "carga_movel" in self.gerenciador.esforcos:
                del self.gerenciador.esforcos["carga_movel"]
            self.gerenciador.esforcos_calculo = None
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_janela_peso_proprio(self):
        dialog = LogicaJanelaPesoProprio(self.gerenciador)
        if dialog.exec():
            self.gerenciador.esforcos_calculo = None
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_janela_sobrecarga(self):
        dialog = LogicaJanelaSobrecarga(self.gerenciador)
        if dialog.exec():
            self.gerenciador.esforcos_calculo = None
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_janela_temperatura(self):
        dialog = LogicaJanelaTemperatura(self.gerenciador)
        if dialog.exec():
            self.gerenciador.esforcos_calculo = None
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_janela_carga_movel(self):
        dialog = LogicaJanelaCargaMovel(self.gerenciador)
        if dialog.exec():
            self.gerenciador.esforcos_calculo = None
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_janela_esforcos_calculo(self):
        dialog = LogicaJanelaEsforcosCalculo(self.gerenciador)
        if dialog.exec():
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_janela_armadura_longitudinal(self):
        dialog = LogicaJanelaArmaduraLongitudinal(self.gerenciador)
        if dialog.exec():
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    def abrir_janela_armadura_transversal(self):
        dialog = LogicaJanelaArmaduraTransversal(self.gerenciador)
        if dialog.exec():
            self.arquivo_controller.marcar_como_modificado()
            self.atualizar_interface()

    # =========================================================================
    # Atualização da interface
    # =========================================================================
    def atualizar_interface(self):
        """
        Lê o estado atual do gerenciador de dados e ajusta os elementos da
        janela principal: habilita/desabilita botões conforme as dependências
        e atualiza os painéis HTML de status de cada etapa.
        """
        sup       = self.gerenciador.get_superestrutura()
        sec       = self.gerenciador.get_secao_transversal()
        sec_super = self.gerenciador.get_secao_superestrutura()
        coef      = self.gerenciador.get_coeficientes_impacto()
        trem      = self.gerenciador.get_trem_tipo_longarina()

        esforco_pp = self.gerenciador.get_esforco("peso_proprio")
        esforco_sc = self.gerenciador.get_esforco("sobrecarga")
        esforco_tp = self.gerenciador.get_esforco("temperatura")
        esforco_cm = self.gerenciador.get_esforco("carga_movel")

        esforcos_calculo_obj = self.gerenciador.get_esforcos_calculo()

        # Etapas concluídas
        etapa1_ok = bool(sup and sec and sec_super)
        etapa2_ok = bool(coef and trem)
        sup_e_hiperestatica = sup is not None and sup.tipo in _TIPOS_HIPERESTATICOS

        tem_pp_sc_cm = bool(esforco_pp and esforco_sc and esforco_cm)
        if sup_e_hiperestatica:
            etapa3_ok = etapa1_ok and etapa2_ok and tem_pp_sc_cm and bool(esforco_tp)
        else:
            etapa3_ok = etapa1_ok and etapa2_ok and tem_pp_sc_cm

        etapa4_ok = bool(esforcos_calculo_obj)

        # --- Habilitação dos botões -------------------------------------------------
        self.definir_super_estrutura.setEnabled(True)
        self.definir_sec_transversal.setEnabled(True)

        self.definir_geometria_super.setEnabled(bool(sec))
        self.coef_impacto.setEnabled(bool(sup and sec))
        self.trem_tipo_longarina.setEnabled(bool(sec_super))

        self.peso_proprio.setEnabled(etapa1_ok)
        self.sobre_carga.setEnabled(etapa1_ok)
        self.temperatura.setEnabled(etapa1_ok and sup_e_hiperestatica)
        self.carga_movel.setEnabled(etapa1_ok and etapa2_ok)
        self.esforcos_calculo.setEnabled(etapa3_ok)

        if hasattr(self, 'armadura_longitudinal'):
            self.armadura_longitudinal.setEnabled(etapa4_ok)
        if hasattr(self, 'armadura_transversal'):
            self.armadura_transversal.setEnabled(etapa4_ok)

        # --- Atualização dos painéis HTML -------------------------------------------
        # Sistema Estrutural
        vao_total = None
        tipo_str  = None
        if sup:
            tipo_str = sup.tipo
            laje = float(sup.laje_transicao) if sup.laje_transicao else 0.0
            if "Múltiplos" in tipo_str:
                vao_total = sum(sup.vaos) + (2 * laje)
            else:
                if len(sup.vaos) > 1:
                    vao_total = sup.vaos[0] + 2 * sum(sup.vaos[1:]) + (2 * laje)
                else:
                    vao_total = sup.vaos[0] + (2 * laje)
        self.html_status_sistema.setText(get_html_status_sistema(tipo_str, vao_total))

        # Seção Transversal
        passeio = sec.passeio if sec else None
        classe  = sec.classe  if sec else None
        self.html_status_secao.setText(get_html_status_secao(passeio, classe))

        # Geometria da Superestrutura
        n_long = sec_super.n_longarinas if sec_super else None
        h_cm   = None
        if sec_super:
            h_cm = sec_super.parametros_geometricos.get(
                "h_total", sec_super.parametros_geometricos.get("h"))
        self.html_status_superestrutura.setText(
            get_html_status_superestrutura(n_long, h_cm, bool(sec)))

        # Coeficientes de Impacto
        self.html_status_coef_impacto.setText(
            get_html_status_coef_impacto(bool(coef), bool(sup), bool(sec)))

        # Trem Tipo
        q_kn, q1_knm, q2_knm = None, None, None
        if trem and trem.caso_critico:
            q_kn   = trem.caso_critico.get("Q")
            q1_knm = trem.caso_critico.get("q1")
            q2_knm = trem.caso_critico.get("q2")
        self.html_trem_tipo.setText(
            get_html_trem_tipo(q_kn, q1_knm, q2_knm, bool(sec_super)))

        # Peso Próprio (g1)
        vl_pp = esforco_pp.valores_limites if esforco_pp else {}
        self.html_esforcos_g1.setText(get_html_esforcos_permanentes(
            "Peso Próprio",
            vl_pp.get("r_max"), vl_pp.get("v_min"), vl_pp.get("v_max"),
            vl_pp.get("m_min"), vl_pp.get("m_max"),
            etapa1_ok
        ))

        # Sobrecarga Permanente (g2)
        vl_sc = esforco_sc.valores_limites if esforco_sc else {}
        self.html_esforcos_g2.setText(get_html_esforcos_permanentes(
            "Sobrecarga Permanente",
            vl_sc.get("r_max"), vl_sc.get("v_min"), vl_sc.get("v_max"),
            vl_sc.get("m_min"), vl_sc.get("m_max"),
            etapa1_ok
        ))

        # Temperatura
        vl_tp = esforco_tp.valores_limites if esforco_tp else {}
        self.html_status_temperatura.setText(get_html_status_temperatura(
            vl_tp.get("r_max"), vl_tp.get("v_min"), vl_tp.get("v_max"),
            vl_tp.get("m_min"), vl_tp.get("m_max"),
            etapa1_ok, sup_e_hiperestatica
        ))

        # Carga Móvel
        vl_cm = esforco_cm.valores_limites if esforco_cm else {}
        self.html_status_carga_movel.setText(get_html_status_carga_movel(
            vl_cm.get("r_max"), vl_cm.get("v_min"), vl_cm.get("v_max"),
            vl_cm.get("m_min"), vl_cm.get("m_max"),
            etapa1_ok, etapa2_ok
        ))

        # Esforços de Cálculo
        calculado = bool(esforcos_calculo_obj)
        self.html_status_esforcos_calculo.setText(
            get_html_status_esforcos_calculo(etapa3_ok, calculado))

        # Armadura Longitudinal
        if hasattr(self, 'html_status_armadura_longitudinal'):
            self.html_status_armadura_longitudinal.setText(
                get_html_status_armadura(esforcos_calculo_ok=etapa4_ok,
                                         armadura="longitudinal")
            )

        # Armadura Transversal
        if hasattr(self, 'html_status_armadura_transversal'):
            self.html_status_armadura_transversal.setText(
                get_html_status_armadura(esforcos_calculo_ok=etapa4_ok,
                                         armadura="transversal")
            )

        # Atualiza o título da janela (pode refletir nome do arquivo)
        self.arquivo_controller._atualizar_titulo_janela()

    # =========================================================================
    # Manual do usuário
    # =========================================================================
    def abrir_manual(self):
        """
        Abre o manual do software no PDFViewer na seção de verificação de
        estacas escavadas.

        Navega diretamente para a página 30 do manual (índice 29 em base 0,
        pois o PyMuPDF (fitz) indexa páginas a partir de zero).
        """
        pdf_path = resource_path(os.path.join("assets", "Manual Girder25 Dark.pdf"))
        viewer = PDFViewer(pdf_path, "Manual: JANELA PRINCIPAL")

        # PyMuPDF usa índice base 0: página 30 do manual = índice 29
        viewer.display_page(30)

        viewer.exec()