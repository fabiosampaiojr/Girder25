import os
import sys
from PyQt6.QtWidgets import QDialog, QLabel, QVBoxLayout
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from ui.janela_inicial import Ui_janela_inicial

def resource_path(relative_path):
    """ Retorna o caminho absoluto para o recurso, funciona em dev e no PyInstaller """
    try:
        # PyInstaller cria uma pasta temporária e armazena o caminho em _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class LogicaInicial(QDialog, Ui_janela_inicial):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        # 1. Configurar Logo
        self._configurar_logo()
        
        # 2. Configurar Botão Avançar
        self.avancar.clicked.connect(self.accept) # accept fecha o dialog com resultado positivo

    def _configurar_logo(self):
        # Substitui o frame por um layout com imagem
        if self.logo.layout() is None:
            layout = QVBoxLayout(self.logo)
            layout.setContentsMargins(0,0,0,0)
        
        lbl_img = QLabel()
        caminho_imagem = resource_path(os.path.join("assets", "logo.png"))
        
        if os.path.exists(caminho_imagem):
            pixmap = QPixmap(caminho_imagem)
            lbl_img.setPixmap(pixmap.scaled(self.logo.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.logo.layout().addWidget(lbl_img)
        else:
            print(f"Erro: Imagem não encontrada em {caminho_imagem}")

    # O evento de fechar (X) já chama close(), que encerra o exec() no main.py, permitindo o fluxo seguir.