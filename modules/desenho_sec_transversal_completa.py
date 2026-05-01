import matplotlib.pyplot as plt
import matplotlib.patches as patches

def desenhar_sec_transversal_completa(classe: str, h_borda: float, h_centro: float, 
                                     n_longarinas: int, h_longarina: float, bw: float, 
                                     h_laje: float, d_extremidade: float, passeio: float = False,
                                     exibir_via: bool = True):
    """
    Gera o desenho técnico consolidado da superestrutura.
    
    Ajustes realizados:
    - Correção definitiva da geometria da via (pavimento e barreiras).
    - Cotas formatadas apenas como 'valor cm'.
    - Polígono da laje construído de forma ortogonal e contínua.
    """
    
    # --- FALLBACK PARA CLASSE PERSONALIZADA ---
    if classe == "Personalizado":
        # Desenho genérico não disponível para classe personalizada
        return None

    # --- 1. CONFIGURAÇÕES DE ESTILO ---
    cor_fundo = '#2b2b2b'
    cor_obj = 'white'
    cor_asfalto = '#3d3d3d'
    cor_concreto = '#a0a0a0'
    cor_estrutura = '#555555'
    
    mapa_classes = {
        "0":     {"faixa": 375, "ac_ext": 300, "ac_int": 60,  "pista_dupla": True},
        "I - A": {"faixa": 360, "ac_ext": 300, "ac_int": 60,  "pista_dupla": True},
        "I - B": {"faixa": 350, "ac_ext": 250, "ac_int": 0,   "pista_dupla": False},
        "II":    {"faixa": 350, "ac_ext": 250, "ac_int": 0,   "pista_dupla": False},
        "III":   {"faixa": 350, "ac_ext": 150, "ac_int": 0,   "pista_dupla": False},
        "IV":    {"faixa": 300, "ac_ext": 150, "ac_int": 0,   "pista_dupla": False},
    }

    config = mapa_classes.get(classe)
    if not config: return

    # --- 2. CÁLCULOS DE GEOMETRIA E ANCORAGEM ---
    f, ae, ai = config["faixa"], config["ac_ext"], config["ac_int"]
    dupla = config["pista_dupla"]
    p = (passeio if passeio else 0)
    l_nj, l_gc = 40, 15 
    
    # Definição dos limites horizontais (X)
    x_face_externa_nj_esq = p
    x_face_interna_nj_esq = x_face_externa_nj_esq + l_nj
    
    # --- AJUSTE: largura entre faces internas conforme composição do tabuleiro ---
    if dupla:
        # Tabuleiro da esquerda: acostamento interno + 2 faixas + acostamento externo
        dist_miolo = ai + 2 * f + ae
    else:
        # Pista simples: acostamento externo esquerdo + 2 faixas + acostamento externo direito
        dist_miolo = 2 * ae + 2 * f
    # -------------------------------------------------------------------------
    
    x_face_interna_nj_dir = x_face_interna_nj_esq + dist_miolo
    x_face_externa_nj_dir = x_face_interna_nj_dir + l_nj
    
    L_total_obra = x_face_externa_nj_dir + (p if (p > 0 and not dupla) else 0)
    
    # Eixos das longarinas
    d_entre_eixos = (L_total_obra - 2 * d_extremidade) / (n_longarinas - 1) if n_longarinas > 1 else 0
    x_eixos = [d_extremidade + (i * d_entre_eixos) for i in range(n_longarinas)]

    # --- 3. INICIALIZAÇÃO DO PLOT ---
    fig, ax = plt.subplots(figsize=(16, 7), facecolor=cor_fundo)
    ax.set_facecolor(cor_fundo)

    # --- 4. FUNÇÕES DE DESENHO E COTA ---
    def cota_h(x1, x2, y, val):
        ax.annotate('', xy=(x1, y), xytext=(x2, y), arrowprops=dict(arrowstyle='<->', color=cor_obj, lw=0.8))
        ax.text((x1+x2)/2, y - 5, f"{val} cm", color=cor_obj, ha='center', va='top', fontsize=8)

    def cota_v(x, y1, y2, val, side='left'):
        ax.annotate('', xy=(x, y1), xytext=(x, y2), arrowprops=dict(arrowstyle='<->', color=cor_obj, lw=0.8))
        ha = 'right' if side == 'left' else 'left'
        ax.text(x - 5 if side == 'left' else x + 5, (y1+y2)/2, f"{val} cm", 
                color=cor_obj, ha=ha, va='center', fontsize=8)

    # --- 5. ESTRUTURA (LAJE + LONGARINAS) ---
    # Contorno da laje e vigas em um polígono único para evitar falhas visuais
    pts_laje = [(0, 0), (L_total_obra, 0), (L_total_obra, -h_laje)]
    for i in range(n_longarinas - 1, -1, -1):
        xe = x_eixos[i]
        pts_laje.extend([
            (xe + bw/2, -h_laje),
            (xe + bw/2, -(h_laje + h_longarina)),
            (xe - bw/2, -(h_laje + h_longarina)),
            (xe - bw/2, -h_laje)
        ])
    pts_laje.extend([(0, -h_laje), (0, 0)])
    ax.add_patch(patches.Polygon(pts_laje, closed=True, ec=cor_obj, fc=cor_estrutura, lw=1.5, zorder=2))

    # --- 6. VIA (PAVIMENTO, NJ E PASSEIOS) ---
    if exibir_via:
        # Pavimento (Asfalto) - Triângulo/Polígono sobre a laje
        larg_pista = x_face_interna_nj_dir - x_face_interna_nj_esq
        meio_x = x_face_interna_nj_esq + larg_pista / 2
        pts_asf = [
            (x_face_interna_nj_esq, 0), 
            (x_face_interna_nj_esq, h_borda), 
            (meio_x, h_centro), 
            (x_face_interna_nj_dir, h_borda), 
            (x_face_interna_nj_dir, 0)
        ]
        ax.add_patch(patches.Polygon(pts_asf, closed=True, ec=cor_obj, fc=cor_asfalto, lw=1, zorder=4))
        
        # New Jersey Esquerda
        pts_nj_e = [(0,0), (40,0), (40,15), (22.5,40), (17.5,87), (0,87)]
        pts_nj_e_g = [(x_face_externa_nj_esq + pt[0], pt[1]) for pt in pts_nj_e]
        ax.add_patch(patches.Polygon(pts_nj_e_g, closed=True, ec=cor_obj, fc=cor_concreto, zorder=5))
        
        # New Jersey Direita
        pts_nj_d = [(40-pt[0], pt[1]) for pt in pts_nj_e]
        pts_nj_d_g = [(x_face_interna_nj_dir + pt[0], pt[1]) for pt in pts_nj_d]
        ax.add_patch(patches.Polygon(pts_nj_d_g, closed=True, ec=cor_obj, fc=cor_concreto, zorder=5))

        # Guarda-corpos e Passeios
        if p > 0:
            ax.add_patch(patches.Rectangle((0, 0), l_gc, 90, ec=cor_obj, fc=cor_concreto, zorder=5))
            if not dupla:
                ax.add_patch(patches.Rectangle((L_total_obra - l_gc, 0), l_gc, 90, ec=cor_obj, fc=cor_concreto, zorder=5))

        # Linha de base da via
        ax.plot([0, L_total_obra], [0, 0], color=cor_obj, lw=1.2, zorder=3)

    # --- 7. COTAGEM TÉCNICA ---
    # Linhas de eixo (Traço-Ponto)
    for x_e in x_eixos:
        ax.plot([x_e, x_e], [h_centro + 20, -(h_laje + h_longarina + 40)], color=cor_obj, ls='-.', lw=0.6, alpha=0.4)

    # Cotas solicitadas:
    # 7.1 Largura bw da primeira longarina
    cota_h(x_eixos[0] - bw/2, x_eixos[0] + bw/2, -(h_laje + h_longarina + 25), f"{bw}")

    # 7.2 Altura da primeira longarina
    cota_v(x_eixos[0] + bw/2 + 10, -h_laje, -(h_laje + h_longarina), f"{h_longarina}", side='right')

    # 7.3 Altura da laje (na extremidade esquerda)
    cota_v(-20, 0, -h_laje, f"{h_laje}")

    # 7.4 Distância centro da última longarina à face externa direita
    cota_h(x_eixos[-1], L_total_obra, -(h_laje + h_longarina + 60), f"{d_extremidade:.1f}")

    # 7.5 Cota entre eixos (Geral)
    y_eixos = -(h_laje + h_longarina + 60)
    for i in range(n_longarinas - 1):
        cota_h(x_eixos[i], x_eixos[i+1], y_eixos, f"{d_entre_eixos:.1f}")

    # --- 8. FINALIZAÇÃO ---
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_xlim(-100, L_total_obra + 100)
    ax.set_ylim(y_eixos - 100, 150)
    plt.tight_layout()
    
    return fig

# Exemplo de uso:
if __name__ == "__main__":
    fig = desenhar_sec_transversal_completa(
        classe="I - A", h_borda=7, h_centro=12, 
        n_longarinas=3, h_longarina=150, bw=40, 
        h_laje=20, d_extremidade=110, passeio=150,
        exibir_via=False
    )
    plt.show()