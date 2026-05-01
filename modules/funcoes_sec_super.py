import matplotlib.pyplot as plt
import matplotlib.patches as patches

def calcular_secao(dados: dict, h_laje: float = None, largura_colaborante: float = None) -> dict:
    """
    Calcula as propriedades geométricas: Área, Ycg (da base), Altura Total e Inércia (Ix).

    Parâmetros adicionais:
        h_laje (float, opcional): Espessura da laje colaborante (cm).
        largura_colaborante (float, opcional): Largura da laje colaborante (cm).
            Quando fornecida, a laje é tratada como elemento adicional acima da seção,
            e os parâmetros Area, ycg, h e Ix passam a refletir a seção composta.
            O retorno sempre inclui "Area Longarina" com a área da seção sem a laje.
    """
    tipo = dados.get("Tipo")
    area = 0.0
    ycg = 0.0
    i_x = 0.0
    h_total = dados.get("h", 0.0)

    componentes = [] 

    if tipo == "Retangular":
        b = dados.get("bw") or dados.get("b")
        h = dados.get("h")
        if not b or not h: 
            for v in dados.values():
                if isinstance(v, tuple): b, h = v
        
        area = b * h
        ycg = h / 2
        i_x = (b * h**3) / 12
        h_total = h

    elif tipo == "T":
        bw, h, bf, hf = dados["bw"], dados["h"], dados["bf"], dados["hf"]
        hw = h - hf
        comp = [
            {"b": bw, "h": hw, "y_base": hw/2},
            {"b": bf, "h": hf, "y_base": h - hf/2}
        ]
        for c in comp:
            a_i = c["b"] * c["h"]
            componentes.append((a_i, c["y_base"], (c["b"] * c["h"]**3)/12))
            area += a_i

    elif tipo == "I":
        bw, h = dados["bw"], dados["h"]
        btf, hft = dados["btf"], dados["hft"]
        bfb, hfb = dados["bfb"], dados["hfb"]
        hw = h - hft - hfb
        
        comp = [
            {"b": bfb, "h": hfb, "y_base": hfb/2},
            {"b": bw,  "h": hw,  "y_base": hfb + hw/2},
            {"b": btf, "h": hft, "y_base": h - hft/2}
        ]
        for c in comp:
            a_i = c["b"] * c["h"]
            componentes.append((a_i, c["y_base"], (c["b"] * c["h"]**3)/12))
            area += a_i

    if tipo in ["T", "I"]:
        ycg = sum(c[0] * c[1] for c in componentes) / area
        i_x = sum(c[2] + c[0] * (c[1] - ycg)**2 for c in componentes)

    # --- Guarda a área da longarina ANTES de considerar a laje colaborante ---
    area_longarina = area

    # --- Composição com laje colaborante (quando fornecida) ---
    if largura_colaborante is not None and h_laje is not None:
        # A laje fica acima da seção: de y = h_total até y = h_total + h_laje
        a_laje = largura_colaborante * h_laje
        y_laje = h_total + h_laje / 2          # centroide da laje medido da base da longarina
        area_total = area + a_laje
        ycg_comp = (area * ycg + a_laje * y_laje) / area_total
        i_laje_prop = (largura_colaborante * h_laje**3) / 12
        i_x_comp = (
            i_x + area * (ycg - ycg_comp)**2
            + i_laje_prop + a_laje * (y_laje - ycg_comp)**2
        )
        area   = area_total
        ycg    = ycg_comp
        i_x    = i_x_comp
        h_total = h_total + h_laje

    return {"Area": area, "Area Longarina": area_longarina, "ycg": ycg, "h": h_total, "Ix": i_x}

def calcular_secao_reversa(h_total: float, i_x: float) -> dict:
    """
    Realiza o processo inverso: a partir das propriedades geométricas,
    calcula a largura (bw) necessária para uma seção retangular 
    ter a mesma inércia informada.
    """
    # Evita divisão por zero
    if h_total <= 0:
        return {"Tipo": "Retangular", "bw": 0.0, "h": 0.0, "Aviso": "Altura inválida"}

    # Cálculo do bw baseado na fórmula da inércia: Ix = (bw * h^3) / 12
    bw_calculado = (12 * i_x) / (h_total**3)
    
    return {
        "Tipo": "Retangular",
        "bw": round(bw_calculado, 2),
        "h": float(h_total)
    }

def desenhar_secao(dados: dict, exibir_cotas: bool = True,
                   h_laje: float = None, largura_colaborante: float = None):
    """
    Gera o desenho técnico da seção transversal isolada.

    Parâmetros
    ----------
    dados : dict
        Dimensões da seção (Tipo, bw/b, h, bf, hf, btf, hft, bfb, hfb).
    exibir_cotas : bool
        Se True, desenha cotas e marcador do CG.
    h_laje : float, opcional
        Espessura da laje colaborante [cm].
    largura_colaborante : float, opcional
        Largura da laje colaborante [cm].

    Retorna
    -------
    matplotlib.figure.Figure
    """
    res_base = calcular_secao(dados)
    res_comp = calcular_secao(dados, h_laje=h_laje, largura_colaborante=largura_colaborante)

    tipo         = dados.get("Tipo")
    h_base       = res_base["h"]
    h_total_comp = res_comp["h"]
    ycg          = res_comp["ycg"]

    # Paleta de cores
    COR_FUNDO    = '#2b2b2b'
    COR_CONCRETO = '#4a4a4a'
    COR_BORDA    = '#e0e0e0'
    COR_LAJE     = '#3a6186'
    COR_LAJE_ED  = '#90CAF9'
    COR_COTA     = '#909090'
    COR_TXT      = '#e0e0e0'
    COR_CG       = '#EF5350'

    # Figura (tamanho FIXO: 331×311 px)
    fig, ax = plt.subplots(figsize=(3.31, 3.11), facecolor=COR_FUNDO, dpi=100)
    ax.set_facecolor(COR_FUNDO)

    # Polígono via função auxiliar
    path_coords = gerar_poligono_secao(dados)
    ax.add_patch(patches.Polygon(
        path_coords, closed=True,
        facecolor=COR_CONCRETO, edgecolor=COR_BORDA,
        lw=1.4, zorder=2, hatch='////'
    ))

    # Laje colaborante com hachura de laje
    if largura_colaborante is not None and h_laje is not None:
        ax.add_patch(patches.Rectangle(
            (-largura_colaborante / 2, h_base), largura_colaborante, h_laje,
            linewidth=1.4, edgecolor=COR_LAJE_ED,
            facecolor=COR_LAJE, zorder=2, alpha=0.80, hatch='..'
        ))

    # Marcador do CG (círculo + cruz)
    if exibir_cotas:
        _r = max(dados.get("bw", dados.get("b", 20)) * 0.04, 2.5)
        ax.add_patch(patches.Circle((0, ycg), _r,
            edgecolor=COR_CG, facecolor='none', lw=1.1, zorder=6))
        ax.plot([-_r*2.2, _r*2.2], [ycg, ycg], color=COR_CG, lw=0.7, zorder=6)
        ax.plot([0, 0], [ycg-_r*2.2, ycg+_r*2.2], color=COR_CG, lw=0.7, zorder=6)

    # Função de cota com linhas de extensão e mutation_scale=1
    def draw_dim(p1, p2, label, offset=10, orientation='h'):
        TICK = max(2.0, offset * 0.20)
        if orientation == 'h':
            y_c = p1[1] + offset
            for xp in (p1[0], p2[0]):
                ax.plot([xp, xp], [y_c - TICK, y_c + TICK], color=COR_COTA, lw=0.6, zorder=3)
            ax.annotate('', xy=(p1[0], y_c), xytext=(p2[0], y_c),
                        arrowprops=dict(arrowstyle='<->', color=COR_COTA, lw=0.6, mutation_scale=1))
            ax.text((p1[0]+p2[0])/2, y_c + TICK*0.8,
                    f"{label}: {abs(p2[0]-p1[0]):.1f}cm",
                    color=COR_TXT, ha='center', va='bottom', fontsize=6,
                    bbox=dict(boxstyle='round,pad=0.12', facecolor=COR_FUNDO,
                              edgecolor=COR_COTA, linewidth=0.4, alpha=0.85))
        else:
            x_c = p1[0] + offset
            for yp in (p1[1], p2[1]):
                ax.plot([x_c - TICK, x_c + TICK], [yp, yp], color=COR_COTA, lw=0.6, zorder=3)
            ax.annotate('', xy=(x_c, p1[1]), xytext=(x_c, p2[1]),
                        arrowprops=dict(arrowstyle='<->', color=COR_COTA, lw=0.6, mutation_scale=1))
            ax.text(x_c + TICK*0.8, (p1[1]+p2[1])/2,
                    f"{label}: {abs(p2[1]-p1[1]):.1f}cm",
                    color=COR_TXT, ha='left', va='center', fontsize=6,
                    bbox=dict(boxstyle='round,pad=0.12', facecolor=COR_FUNDO,
                              edgecolor=COR_COTA, linewidth=0.4, alpha=0.85))

    # Cotas por tipo de seção
    if exibir_cotas:
        h = res_base["h"]
        if tipo == "Retangular":
            b = dados.get("bw") or dados.get("b")
            draw_dim((-b/2, 0), (b/2, 0), "bw", -15)
            draw_dim((b/2, 0), (b/2, h), "h", 15, 'v')
        elif tipo == "T":
            draw_dim((-dados['bf']/2, h), (dados['bf']/2, h), "bf", 15)
            draw_dim((dados['bf']/2, h-dados['hf']), (dados['bf']/2, h), "hf", 10, 'v')
            draw_dim((dados['bw']/2, 0), (dados['bw']/2, h-dados['hf']), "hw", 10, 'v')
            draw_dim((-dados['bw']/2, 0), (dados['bw']/2, 0), "bw", -15)
        elif tipo == "I":
            bw, btf, bfb = dados['bw'], dados['btf'], dados['bfb']
            hft, hfb = dados['hft'], dados['hfb']
            hw = h - hft - hfb
            draw_dim((-btf/2, h), (btf/2, h), "btf", 15)
            draw_dim((-bfb/2, 0), (bfb/2, 0), "bfb", -15)
            draw_dim((-bw/2, hfb + hw/2), (bw/2, hfb + hw/2), "bw", -15)
            offset_dir = max(btf, bfb)/2 + 10
            draw_dim((offset_dir, h - hft), (offset_dir, h), "hft", 0, 'v')
            draw_dim((offset_dir, hfb), (offset_dir, h - hft), "hw", 0, 'v')
            draw_dim((offset_dir, 0), (offset_dir, hfb), "hfb", 0, 'v')
        if largura_colaborante is not None and h_laje is not None:
            lc = largura_colaborante
            draw_dim((-lc/2, h_base + h_laje), (lc/2, h_base + h_laje), "lc", 15)
            draw_dim((lc/2, h_base), (lc/2, h_base + h_laje), "h_laje", 15, 'v')

    # Limites automáticos com margem
    meia_largura      = max(dados.get("bf", 0)/2, dados.get("btf", 0)/2,
                            dados.get("bfb", 0)/2, dados.get("bw", 0)/2, 25)
    meia_largura_laje = (largura_colaborante / 2) if largura_colaborante is not None else 0
    x_min_poly = -max(meia_largura, meia_largura_laje)
    x_max_poly =  max(meia_largura, meia_largura_laje)
    x_min, x_max = x_min_poly, x_max_poly
    y_min, y_max = 0, h_total_comp

    if exibir_cotas:
        if tipo == "Retangular":
            y_min = min(y_min, -15); y_max = max(y_max, h_base + 15)
            x_max = max(x_max, meia_largura + 15)
        elif tipo == "T":
            y_min = min(y_min, -15); y_max = max(y_max, h_base + 15)
            x_max = max(x_max, meia_largura + 10)
        elif tipo == "I":
            y_min = min(y_min, -15); y_max = max(y_max, h_base + 15)
            offset_dir = max(dados.get('btf', 0), dados.get('bfb', 0))/2 + 10
            x_max = max(x_max, offset_dir)
        if largura_colaborante is not None and h_laje is not None:
            y_max = max(y_max, h_total_comp + 15)
            x_max = max(x_max, meia_largura_laje + 15)

    margem = 20
    x_min = min(x_min, -max(meia_largura, meia_largura_laje)) - margem
    x_max = max(x_max,  max(meia_largura, meia_largura_laje)) + margem
    y_min = min(y_min, 0) - margem
    y_max = max(y_max, h_total_comp) + margem

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect('equal')
    ax.axis('off')
    plt.tight_layout()
    return fig

def gerar_poligono_secao(dados: dict):
    """
    Gera a lista de coordenadas (x, y) do polígono que representa a seção transversal,
    com a seção centrada em x = 0 e com a base inferior em y = 0.
    
    Parâmetros:
        dados (dict): Dicionário com as dimensões da seção (Tipo, b, h, etc.)
    
    Retorna:
        list: Lista de tuplas (x, y) dos vértices do polígono (fechado, sentido horário).
    """
    tipo = dados.get("Tipo")
    path_coords = []

    if tipo == "Retangular":
        b = dados.get("bw") or dados.get("b")
        h = dados.get("h")
        path_coords = [
            (-b / 2, 0),   # canto inferior esquerdo
            (b / 2, 0),    # canto inferior direito
            (b / 2, h),    # canto superior direito
            (-b / 2, h)    # canto superior esquerdo
        ]

    elif tipo == "T":
        bw = dados["bw"]
        h = dados["h"]
        bf = dados["bf"]
        hf = dados["hf"]
        hw = h - hf  # altura da alma
        path_coords = [
            (-bw / 2, 0),          # base da alma (esq)
            (bw / 2, 0),           # base da alma (dir)
            (bw / 2, hw),          # topo da alma (dir)
            (bf / 2, hw),          # transição para mesa (dir)
            (bf / 2, h),            # topo da mesa (dir)
            (-bf / 2, h),           # topo da mesa (esq)
            (-bf / 2, hw),          # transição para alma (esq)
            (-bw / 2, hw)           # topo da alma (esq)
        ]

    elif tipo == "I":
        bw = dados["bw"]
        h = dados["h"]
        btf = dados["btf"]
        hft = dados["hft"]
        bfb = dados["bfb"]
        hfb = dados["hfb"]
        hw = h - hft - hfb
        path_coords = [
            (-bfb / 2, 0),               # mesa inferior (esq)
            (bfb / 2, 0),                # mesa inferior (dir)
            (bfb / 2, hfb),               # transição alma (dir)
            (bw / 2, hfb),                # alma (dir)
            (bw / 2, h - hft),            # transição mesa superior (dir)
            (btf / 2, h - hft),           # mesa superior (dir)
            (btf / 2, h),                  # topo mesa superior (dir)
            (-btf / 2, h),                 # topo mesa superior (esq)
            (-btf / 2, h - hft),           # mesa superior (esq)
            (-bw / 2, h - hft),            # transição alma (esq)
            (-bw / 2, hfb),                # alma (esq)
            (-bfb / 2, hfb)                # mesa inferior (esq)
        ]

    return path_coords

def desenhar_sec_transversal_completa(classe: str, h_borda: float, h_centro: float,
                                     n_longarinas: int, h_laje: float, d_extremidade: float,
                                     dados: dict, area_longarina: float,
                                     passeio: float = False,
                                     exibir_via: bool = True,
                                     config_personalizado: dict = None):
    """
    Gera o desenho técnico consolidado da superestrutura com longarinas detalhadas.

    Parâmetros
    ----------
    classe : str
        Classe da via (ex: "0", "I - A", "II", "Personalizado", etc.)
    h_borda : float
        Altura do pavimento nas bordas [cm].
    h_centro : float
        Altura do pavimento no centro [cm].
    n_longarinas : int
        Número de longarinas.
    h_laje : float
        Espessura da laje [cm].
    d_extremidade : float
        Distância do centro da longarina extrema até a face externa [cm].
    dados : dict
        Dicionário com dimensões da seção da longarina.
    area_longarina : float
        Área da seção da longarina [cm²] (exibida na anotação).
    passeio : float
        Largura do passeio [cm] (0 = sem passeio).
    exibir_via : bool
        Se True, desenha pavimento, NJ e passeios.
    config_personalizado : dict, opcional
        Dicionário com as dimensões da via quando classe == "Personalizado".
        Espera as chaves: "faixa", "ac_ext", "ac_int", "pista_dupla".

    Retorna
    -------
    matplotlib.figure.Figure
    """
    # Paleta de cores
    COR_FUNDO    = '#2b2b2b'
    COR_CONTORNO = '#e0e0e0'
    COR_ASFALTO  = '#3c3c3c'
    COR_CONCRETO = '#9e9e9e'
    COR_STRUCT   = '#4a4a4a'
    COR_COTA     = '#909090'
    COR_TXT      = '#e0e0e0'
    COR_EIXO     = '#FFA726'   # traço-ponto das linhas de eixo

    # Mapeamento das classes de via (NBR 7188 / DNIT) – usado para classes normais
    mapa_classes = {
        "0":     {"faixa": 375, "ac_ext": 300, "ac_int": 60,  "pista_dupla": True},
        "I - A": {"faixa": 360, "ac_ext": 300, "ac_int": 60,  "pista_dupla": True},
        "I - B": {"faixa": 350, "ac_ext": 250, "ac_int": 0,   "pista_dupla": False},
        "II":    {"faixa": 350, "ac_ext": 250, "ac_int": 0,   "pista_dupla": False},
        "III":   {"faixa": 350, "ac_ext": 150, "ac_int": 0,   "pista_dupla": False},
        "IV":    {"faixa": 300, "ac_ext": 150, "ac_int": 0,   "pista_dupla": False},
    }

    # Determina as dimensões da via de acordo com a classe
    if classe == "Personalizado":
        if config_personalizado is None:
            return None  # sem dados não é possível desenhar
        f     = config_personalizado["faixa"]
        ae    = config_personalizado["ac_ext"]
        ai    = config_personalizado["ac_int"]
        dupla = config_personalizado["pista_dupla"]
    else:
        config = mapa_classes.get(classe)
        if not config:
            raise ValueError(f"Classe '{classe}' não reconhecida.")
        f     = config["faixa"]
        ae    = config["ac_ext"]
        ai    = config["ac_int"]
        dupla = config["pista_dupla"]

    p     = passeio if passeio else 0
    l_nj, l_gc = 40, 15

    # Limites horizontais
    x_face_externa_nj_esq = p
    x_face_interna_nj_esq = x_face_externa_nj_esq + l_nj
    dist_miolo = (ai + 2 * f + ae) if dupla else (2 * ae + 2 * f)
    x_face_interna_nj_dir = x_face_interna_nj_esq + dist_miolo
    x_face_externa_nj_dir = x_face_interna_nj_dir + l_nj
    L_total_obra = x_face_externa_nj_dir + (p if (p > 0 and not dupla) else 0)

    # Eixos das longarinas
    d_entre_eixos = (L_total_obra - 2 * d_extremidade) / (n_longarinas - 1) if n_longarinas > 1 else 0
    x_eixos = [d_extremidade + i * d_entre_eixos for i in range(n_longarinas)]

    res_long  = calcular_secao(dados)
    h_longarina = res_long["h"]
    tipo      = dados.get("Tipo")

    # Figura (tamanho FIXO: 961×541 px)
    fig, ax = plt.subplots(figsize=(9.61, 5.41), facecolor=COR_FUNDO, dpi=100)
    ax.set_facecolor(COR_FUNDO)

    # Laje (retângulo com hachura de concreto)
    ax.add_patch(patches.Rectangle(
        (0, -h_laje), L_total_obra, h_laje,
        linewidth=1.4, edgecolor=COR_CONTORNO,
        facecolor=COR_STRUCT, zorder=2, hatch='////'
    ))

    # Longarinas com hachura
    for x_e in x_eixos:
        poly_pts  = gerar_poligono_secao(dados)
        poly_trans = [(x + x_e, y - h_laje - h_longarina) for (x, y) in poly_pts]
        ax.add_patch(patches.Polygon(
            poly_trans, closed=True,
            linewidth=1.3, edgecolor=COR_CONTORNO,
            facecolor=COR_STRUCT, zorder=2, hatch='////'
        ))

    # Pavimento e barreiras NJ
    if exibir_via:
        # Perfil de pavimento parabólico
        import numpy as np
        larg_pista  = x_face_interna_nj_dir - x_face_interna_nj_esq
        meio_x      = x_face_interna_nj_esq + larg_pista / 2
        n_pts       = 60
        xs_pav      = np.linspace(x_face_interna_nj_esq, x_face_interna_nj_dir, n_pts)
        ys_pav      = h_borda + (h_centro - h_borda) * (
            1.0 - ((xs_pav - meio_x) / (larg_pista / 2)) ** 2
        )
        pav_x = [x_face_interna_nj_esq] + list(xs_pav) + [x_face_interna_nj_dir]
        pav_y = [0.0]                   + list(ys_pav) + [0.0]
        ax.add_patch(patches.Polygon(
            list(zip(pav_x, pav_y)), closed=True,
            edgecolor=COR_CONTORNO, facecolor=COR_ASFALTO, lw=1.0, zorder=4
        ))
        ax.plot(xs_pav, ys_pav, color=COR_CONTORNO, lw=1.0, zorder=5)

        # New Jersey – perfil NBR
        _nj_base = [(0,0),(40,0),(40,15),(22.5,40),(17.5,87),(0,87)]
        def draw_nj(x_ini, espelhado=False):
            pts_local = _nj_base if not espelhado else [(40-px, py) for (px,py) in _nj_base]
            pts_g = [(x_ini + px, py) for (px,py) in pts_local]
            ax.add_patch(patches.Polygon(
                pts_g, closed=True,
                edgecolor=COR_CONTORNO, facecolor=COR_CONCRETO, lw=1.2, zorder=5
            ))

        draw_nj(x_face_externa_nj_esq, espelhado=False)
        draw_nj(x_face_interna_nj_dir, espelhado=True)

        # Guarda-corpos / passeios
        if p > 0:
            ax.add_patch(patches.Rectangle(
                (0, 0), l_gc, 90,
                edgecolor=COR_CONTORNO, facecolor=COR_CONCRETO, zorder=5
            ))
            if not dupla:
                ax.add_patch(patches.Rectangle(
                    (L_total_obra - l_gc, 0), l_gc, 90,
                    edgecolor=COR_CONTORNO, facecolor=COR_CONCRETO, zorder=5
                ))

        # Linha de base da via
        ax.plot([0, L_total_obra], [0, 0], color=COR_CONTORNO, lw=1.2, zorder=3)

    # Linhas de eixo (traço-ponto laranja suave)
    for x_e in x_eixos:
        ax.plot([x_e, x_e],
                [h_centro + 25, -(h_laje + h_longarina + 45)],
                color=COR_EIXO, ls='-.', lw=0.7, alpha=0.45, zorder=1)

    # Anotação da área da longarina (seta com caixa)
    if n_longarinas > 0:
        x_e      = x_eixos[0]
        y_centro = -h_laje - h_longarina / 2
        meia_larg_max = max(
            dados.get("bf", 0)/2, dados.get("btf", 0)/2,
            dados.get("bfb", 0)/2, dados.get("bw", 0)/2,
            dados.get("b", 0)/2, 20.0
        )
        offset_seta = meia_larg_max + 45
        ax.annotate(
            f"A = {area_longarina:.2f} cm²",
            xy=(x_e + meia_larg_max, y_centro),
            xytext=(x_e + offset_seta, y_centro + 25),
            color=COR_TXT, fontsize=7.5, va='center', ha='left',
            arrowprops=dict(arrowstyle='->', color=COR_CONTORNO, lw=0.8),
            bbox=dict(boxstyle='round,pad=0.20', facecolor='#383838',
                      edgecolor=COR_CONTORNO, linewidth=0.5, alpha=0.90)
        )

    # Funções de cota técnica com linhas de extensão e mutation_scale=1
    def cota_h(x1, x2, y, val):
        TICK = 4.0
        for xp in (x1, x2):
            ax.plot([xp, xp], [y - TICK, y + TICK], color=COR_COTA, lw=0.6, zorder=3)
        ax.annotate('', xy=(x1, y), xytext=(x2, y),
                    arrowprops=dict(arrowstyle='<->', color=COR_COTA, lw=0.7, mutation_scale=1))
        ax.text((x1+x2)/2, y - TICK*1.2, f"{val} cm",
                color=COR_TXT, ha='center', va='top', fontsize=7,
                bbox=dict(boxstyle='round,pad=0.15', facecolor='#2b2b2b',
                          edgecolor=COR_COTA, linewidth=0.4, alpha=0.85))

    def cota_v(x, y1, y2, val, side='left'):
        TICK = 4.0
        for yp in (y1, y2):
            ax.plot([x - TICK, x + TICK], [yp, yp], color=COR_COTA, lw=0.6, zorder=3)
        ax.annotate('', xy=(x, y1), xytext=(x, y2),
                    arrowprops=dict(arrowstyle='<->', color=COR_COTA, lw=0.7, mutation_scale=1))
        ha = 'right' if side == 'left' else 'left'
        off = -TICK*1.2 if side == 'left' else TICK*1.2
        ax.text(x + off, (y1+y2)/2, f"{val} cm",
                color=COR_TXT, ha=ha, va='center', fontsize=7,
                bbox=dict(boxstyle='round,pad=0.15', facecolor='#2b2b2b',
                          edgecolor=COR_COTA, linewidth=0.4, alpha=0.85))

    y_eixos = -(h_laje + h_longarina + 60)
    # Cota da distância à extremidade (último eixo → borda direita)
    cota_h(x_eixos[-1], L_total_obra, y_eixos, f"{d_extremidade:.1f}")
    # Cotas entre eixos
    for i in range(n_longarinas - 1):
        cota_h(x_eixos[i], x_eixos[i+1], y_eixos, f"{d_entre_eixos:.1f}")
    # Cota vertical da laje (extremidade esquerda)
    cota_v(-22, 0, -h_laje, f"{h_laje:.1f}", side='left')

    # Enquadramento
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_xlim(-100, L_total_obra + 100)
    ax.set_ylim(y_eixos - 80, 160)
    plt.tight_layout()
    return fig

# ============================================================================
# NOVO: GERAÇÃO DO MEMORIAL DE CÁLCULO
# ============================================================================
def gerar_memorial_propriedades_secao(dados: dict, is_personalizada: bool, h_laje: float = None, largura_colaborante: float = None, dados_pers: dict = None) -> str:
    """
    Gera o memorial de cálculo detalhado em HTML das propriedades geométricas da seção,
    acompanhando passo a passo as equações do Teorema de Steiner. Estilo visual consistente
    com o sistema adotado no software.
    """
    tipo = dados.get("Tipo", "Retangular")
    h_total = dados.get("h", 0.0)
    
    # 1. Obter Componentes Discretizados da Seção
    componentes = []
    area_base = 0.0
    
    if not is_personalizada:
        if tipo == "Retangular":
            b = dados.get("bw") or dados.get("b", 0)
            h = dados.get("h", 0)
            componentes.append({"nome": "Retângulo", "b": b, "h": h, "y_base": h/2})
            area_base = b * h
            
        elif tipo == "T":
            bw, h, bf, hf = dados.get("bw",0), dados.get("h",0), dados.get("bf",0), dados.get("hf",0)
            hw = h - hf
            componentes.append({"nome": "Alma", "b": bw, "h": hw, "y_base": hw/2})
            componentes.append({"nome": "Mesa", "b": bf, "h": hf, "y_base": h - hf/2})
            for c in componentes:
                area_base += c["b"] * c["h"]
                
        elif tipo == "I":
            bw, h = dados.get("bw",0), dados.get("h",0)
            btf, hft = dados.get("btf",0), dados.get("hft",0)
            bfb, hfb = dados.get("bfb",0), dados.get("hfb",0)
            hw = h - hft - hfb
            componentes.append({"nome": "Mesa Inf.", "b": bfb, "h": hfb, "y_base": hfb/2})
            componentes.append({"nome": "Alma", "b": bw,  "h": hw,  "y_base": hfb + hw/2})
            componentes.append({"nome": "Mesa Sup.", "b": btf, "h": hft, "y_base": h - hft/2})
            for c in componentes:
                area_base += c["b"] * c["h"]

    # 2. Raciocínio Base (Área, Ycg, Inércia Base)
    ycg_base = 0.0
    ix_base = 0.0
    html_componentes = ""
    
    if is_personalizada and dados_pers:
        area_base = dados_pers.get("Area", 0)
        ix_base = dados_pers.get("Ix", 0)
        ycg_base = dados_pers.get("h", 0) / 2
        h_total = dados_pers.get("h", 0)
        
        html_componentes = f"""
        <div class="info-box">
            <p><strong>Seção Personalizada:</strong> Os dados da longarina foram inseridos diretamente pelo usuário.</p>
            <p>A = <strong>{area_base:.2f} cm²</strong></p>
            <p>I<sub>x</sub> = <strong>{ix_base:.2f} cm⁴</strong></p>
            <p>Altura (h) = <strong>{h_total:.2f} cm</strong> &nbsp;|&nbsp; Y<sub>cg</sub> adotado no centro geométrico = <strong>{ycg_base:.2f} cm</strong></p>
        </div>
        """
    else:
        # Calcular Ycg da base
        momento_estatico_total = sum((c["b"] * c["h"]) * c["y_base"] for c in componentes)
        ycg_base = momento_estatico_total / area_base if area_base > 0 else 0
        
        # Gerar linhas da tabela de componentes e Steiner
        linhas_tabela = ""
        for i, c in enumerate(componentes, 1):
            A_i = c["b"] * c["h"]
            I_prop = (c["b"] * c["h"]**3) / 12
            d = c["y_base"] - ycg_base
            I_steiner = A_i * (d ** 2)
            I_final = I_prop + I_steiner
            ix_base += I_final
            
            linhas_tabela += f"""
            <tr>
                <td>{i}</td><td>{c['nome']}</td>
                <td>{c['b']:.2f}</td><td>{c['h']:.2f}</td>
                <td>{A_i:.2f}</td><td>{c['y_base']:.2f}</td>
                <td>{d:.2f}</td>
                <td>{I_prop:.2f}</td><td>{I_steiner:.2f}</td>
                <td><strong>{I_final:.2f}</strong></td>
            </tr>
            """
            
        html_componentes = f"""
        <p class="sub-title">► Cálculo do Centro de Gravidade (Y<sub>cg</sub>)</p>
        <p class="formula-eq">Y<sub>cg</sub> = &Sigma;(A<sub>i</sub> &middot; y<sub>i</sub>) / &Sigma;A<sub>i</sub>
            = {momento_estatico_total:.2f} / {area_base:.2f} = <strong>{ycg_base:.2f} cm</strong></p>
        
        <p class="sub-title">► Teorema dos Eixos Paralelos (Teorema de Steiner)</p>
        <p>A inércia total é a soma das inércias próprias mais o produto das áreas pelo quadrado das distâncias ao centroide geral.</p>
        <p class="formula-eq">I<sub>x</sub> = &Sigma; [ I<sub>proprio</sub> + A<sub>i</sub> &middot; (Y<sub>cg,base</sub> - y<sub>i</sub>)&sup2; ]</p>
        <div style="overflow-x:auto;">
        <table>
            <thead><tr>
                <th>#</th><th>Componente</th><th>b [cm]</th><th>h [cm]</th>
                <th>Área [cm²]</th><th>y_base [cm]</th><th>Distância d [cm]</th>
                <th>I_proprio [cm⁴]</th><th>A&middot;d&sup2; [cm⁴]</th><th>I_parcial [cm⁴]</th>
            </tr></thead>
            <tbody>{linhas_tabela}</tbody>
        </table>
        </div>
        <p>I<sub>x,base</sub> total = <strong>{ix_base:.2f} cm⁴</strong></p>
        """

    # 3. Composição com a Laje Colaborante (Se houver)
    html_composta = ""
    area_final = area_base
    ycg_final = ycg_base
    ix_final = ix_base
    h_final = h_total
    
    if largura_colaborante is not None and h_laje is not None:
        a_laje = largura_colaborante * h_laje
        y_laje = h_total + (h_laje / 2) # cg da laje medido da base da longarina
        area_final = area_base + a_laje
        ycg_final = (area_base * ycg_base + a_laje * y_laje) / area_final
        
        i_laje_prop = (largura_colaborante * h_laje**3) / 12
        d_long = ycg_base - ycg_final
        d_laje = y_laje - ycg_final
        
        ix_long_comp = ix_base + area_base * (d_long**2)
        ix_laje_comp = i_laje_prop + a_laje * (d_laje**2)
        ix_final = ix_long_comp + ix_laje_comp
        h_final = h_total + h_laje

        html_composta = f"""
        <div class="section">
            <div class="section-title">🧱 SEÇÃO 2 – Composição com Laje Colaborante</div>
            <div class="grid-2">
                <div>
                    <p class="sub-title">Propriedades da Laje</p>
                    <table>
                        <tr><td>b_colaborante</td><td>{largura_colaborante:.2f} cm</td></tr>
                        <tr><td>h_laje</td><td>{h_laje:.2f} cm</td></tr>
                        <tr><td>Área Laje (A_L)</td><td>{a_laje:.2f} cm²</td></tr>
                        <tr><td>Y_cg da Laje</td><td>{y_laje:.2f} cm (desde a base)</td></tr>
                        <tr><td>I_proprio Laje</td><td>{i_laje_prop:.2f} cm⁴</td></tr>
                    </table>
                </div>
            </div>
            
            <p class="sub-title">► Novo Centro de Gravidade da Seção Composta</p>
            <p class="formula-eq">Y<sub>cg,comp</sub> = (A<sub>long</sub> &middot; Y<sub>long</sub> + A<sub>laje</sub> &middot; Y<sub>laje</sub>) / A<sub>total</sub>
                = ({area_base:.2f} &middot; {ycg_base:.2f} + {a_laje:.2f} &middot; {y_laje:.2f}) / {area_final:.2f}
                = <strong>{ycg_final:.2f} cm</strong></p>
                
            <p class="sub-title">► Inércia da Seção Composta (Steiner)</p>
            <div style="overflow-x:auto;">
            <table>
                <thead><tr>
                    <th>Elemento</th><th>Inércia Base [cm⁴]</th><th>Área [cm²]</th>
                    <th>Y_cg [cm]</th><th>Distância cg_comp [cm]</th><th>A&middot;d&sup2; [cm⁴]</th>
                    <th>Inércia Parcial [cm⁴]</th>
                </tr></thead>
                <tbody>
                    <tr>
                        <td style="text-align:left;">Longarina</td>
                        <td>{ix_base:.2f}</td><td>{area_base:.2f}</td><td>{ycg_base:.2f}</td>
                        <td>{d_long:.2f}</td><td>{area_base * (d_long**2):.2f}</td>
                        <td><strong>{ix_long_comp:.2f}</strong></td>
                    </tr>
                    <tr>
                        <td style="text-align:left;">Laje Colaborante</td>
                        <td>{i_laje_prop:.2f}</td><td>{a_laje:.2f}</td><td>{y_laje:.2f}</td>
                        <td>{d_laje:.2f}</td><td>{a_laje * (d_laje**2):.2f}</td>
                        <td><strong>{ix_laje_comp:.2f}</strong></td>
                    </tr>
                </tbody>
            </table>
            </div>
            <p>I<sub>x,comp</sub> total = <strong>{ix_final:.2f} cm⁴</strong></p>
        </div>
        """

    # 4. Estruturação do HTML Completo
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #0f172a; color: #e2e8f0; padding: 20px; font-size: 14px; line-height: 1.6; }}
    .container {{ max-width: 1000px; margin: 0 auto; background: #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }}
    .header {{ background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #1a237e 100%); padding: 28px; text-align: center; color: white; }}
    .header h1 {{ margin: 0 0 6px 0; font-size: 1.55em; letter-spacing: 0.5px; }}
    .header p  {{ margin: 0; opacity: 0.8; font-size: 0.92em; }}
    .content {{ padding: 28px; }}
    .section {{ margin-bottom: 28px; border-left: 4px solid #3b82f6; padding: 18px 18px 18px 20px; background: rgba(30,40,60,0.5); border-radius: 0 10px 10px 0; }}
    .section-title {{ font-size: 1.15em; font-weight: bold; color: #93c5fd; margin-bottom: 14px; border-bottom: 1px solid #334155; padding-bottom: 8px; }}
    .sub-title {{ color: #7dd3fc; font-weight: bold; margin: 18px 0 8px 0; font-size: 0.98em; }}
    .info-box {{ background: rgba(15,23,42,0.6); border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; border-left: 3px solid #6366f1; }}
    .formula-eq {{ background: #0f172a; border-left: 3px solid #f59e0b; padding: 10px 14px; font-family: 'Courier New', monospace; color: #fef3c7; font-size: 0.93em; margin: 8px 0; border-radius: 0 6px 6px 0; white-space: pre-wrap; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 0.88em; }}
    th {{ background: #1e3a5f; color: #93c5fd; padding: 7px 10px; text-align: center; border-bottom: 2px solid #3b82f6; }}
    td {{ padding: 6px 10px; border-bottom: 1px solid #1e293b; text-align: center; }}
    tr:hover td {{ background: rgba(59,130,246,0.08); }}
    .footer {{ background: #0f172a; padding: 14px; text-align: center; color: #475569; font-size: 0.82em; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>⚙️ Memorial de Cálculo – Propriedades Geométricas da Seção</h1>
        <p>Cálculo detalhado de Área, Centro de Gravidade e Inércia (I<sub>x</sub>)</p>
    </div>
    <div class="content">

        <div class="section">
            <div class="section-title">📐 SEÇÃO 1 – Longarina (Seção Base)</div>
            <p>Tipo de Seção Analisada: <strong>{tipo}</strong></p>
            {html_componentes}
        </div>

        {html_composta}

        <div class="section">
            <div class="section-title">✅ SEÇÃO 3 – Síntese das Propriedades Finais</div>
            <div style="overflow-x:auto;">
            <table>
                <thead><tr>
                    <th>Parâmetro</th><th>Símbolo</th><th>Valor</th><th>Unidade</th>
                </tr></thead>
                <tbody>
                    <tr><td style="text-align:left;">Área Total da Seção</td><td>A</td><td><strong>{area_final:.2f}</strong></td><td>cm²</td></tr>
                    <tr><td style="text-align:left;">Área Apenas Longarina</td><td>A<sub>long</sub></td><td><strong>{area_base:.2f}</strong></td><td>cm²</td></tr>
                    <tr><td style="text-align:left;">Altura Total</td><td>h<sub>tot</sub></td><td><strong>{h_final:.2f}</strong></td><td>cm</td></tr>
                    <tr><td style="text-align:left;">Centro de Gravidade (da base)</td><td>Y<sub>cg</sub></td><td><strong>{ycg_final:.2f}</strong></td><td>cm</td></tr>
                    <tr><td style="text-align:left;">Momento de Inércia Eixo-X</td><td>I<sub>x</sub></td><td><strong>{ix_final:.2f}</strong></td><td>cm⁴</td></tr>
                </tbody>
            </table>
            </div>
        </div>

    </div>
    <div class="footer">
        Memorial de Cálculo gerado automaticamente pelo Software
    </div>
</div>
</body>
</html>
"""
    return html