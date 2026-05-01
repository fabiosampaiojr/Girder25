# ============================================================================
# LOGICA_ARQUIVO.PY - Gerenciamento de Arquivos (Novo, Abrir, Salvar, Salvar Como)
# ============================================================================

import os
from PyQt6.QtWidgets import QFileDialog, QMessageBox

class LogicaArquivo:
    def __init__(self, parent, gerenciador):
        """
        Controlador de arquivo para o software Girder25.

        :param parent: Janela principal (QMainWindow)
        :param gerenciador: Instância do DataManager (Gerenciador_Dados)
        """
        self.parent = parent
        self.gerenciador = gerenciador

        self.caminho_arquivo_atual = None
        self.modificado = False

        # Filtro de arquivos com extensão personalizada .Girder25
        self.filtro_arquivo = "Arquivos Girder25 (*.Girder25);;Todos os arquivos (*.*)"

    def marcar_como_modificado(self):
        """Chamado sempre que o projeto sofre alterações."""
        self.modificado = True
        self._atualizar_titulo_janela()

    def _atualizar_titulo_janela(self):
        """Atualiza o título da janela principal com o nome do arquivo e indicador de modificação."""
        nome_arquivo = "Novo Projeto" if not self.caminho_arquivo_atual else os.path.basename(self.caminho_arquivo_atual)
        asterisco = "*" if self.modificado else ""
        self.parent.setWindowTitle(f"Girder25 - {nome_arquivo}{asterisco}")

    def novo_arquivo(self):
        """Ação: Novo Arquivo."""
        if not self.verificar_salvamento_pendente():
            return False

        self.gerenciador.limpar_dados()
        self.caminho_arquivo_atual = None
        self.modificado = False

        # Atualiza a interface da janela principal
        self.parent.atualizar_interface()
        self._atualizar_titulo_janela()
        return True

    def abrir_arquivo(self):
        """Ação: Abrir Arquivo."""
        if not self.verificar_salvamento_pendente():
            return False

        caminho, _ = QFileDialog.getOpenFileName(
            self.parent,
            "Abrir Projeto",
            "",
            self.filtro_arquivo
        )

        if caminho:
            try:
                self.gerenciador.importar_dados(caminho)
                self.caminho_arquivo_atual = caminho
                self.modificado = False

                self.parent.atualizar_interface()
                self._atualizar_titulo_janela()
                return True
            except Exception as e:
                QMessageBox.critical(self.parent, "Erro", f"Erro ao abrir arquivo:\n{e}")
        return False

    def salvar_arquivo(self):
        """Ação: Salvar."""
        if self.caminho_arquivo_atual:
            try:
                self.gerenciador.exportar_dados(self.caminho_arquivo_atual)
                self.modificado = False
                self._atualizar_titulo_janela()
                return True
            except Exception as e:
                QMessageBox.critical(self.parent, "Erro", f"Erro ao salvar:\n{e}")
                return False
        else:
            return self.salvar_arquivo_como()

    def salvar_arquivo_como(self):
        """Ação: Salvar Como."""
        caminho, _ = QFileDialog.getSaveFileName(
            self.parent,
            "Salvar Projeto",
            "Projeto.Girder25",
            self.filtro_arquivo
        )

        if caminho:
            # Garante a extensão .Girder25
            if not caminho.endswith('.Girder25'):
                caminho += '.Girder25'

            try:
                self.gerenciador.exportar_dados(caminho)
                self.caminho_arquivo_atual = caminho
                self.modificado = False
                self._atualizar_titulo_janela()
                return True
            except Exception as e:
                QMessageBox.critical(self.parent, "Erro", f"Erro ao salvar:\n{e}")
        return False

    def verificar_salvamento_pendente(self):
        """
        Verifica se há alterações não salvas.
        Retorna True se puder prosseguir (salvou, descartou ou não havia modificações).
        Retorna False se o usuário cancelou a operação.
        """
        if not self.modificado:
            return True

        resposta = QMessageBox.warning(
            self.parent,
            "Alterações não salvas",
            "Deseja salvar as alterações no projeto atual?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
        )

        if resposta == QMessageBox.StandardButton.Save:
            return self.salvar_arquivo()
        elif resposta == QMessageBox.StandardButton.Discard:
            return True
        else:  # Cancel
            return False