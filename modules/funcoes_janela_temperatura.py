import matplotlib.pyplot as plt
import matplotlib.patches as patches
import re
import math


def calcular_secao(dados: dict, h_laje: float = None, largura_colaborante: float = None) -> dict:
    # Mantida exatamente a sua lógica original
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

    area_longarina = area

    if largura_colaborante is not None and h_laje is not None:
        a_laje = largura_colaborante * h_laje
        y_laje = h_total + h_laje / 2
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
    if h_total <= 0:
        return {"Tipo": "Retangular", "bw": 0.0, "h": 0.0, "Aviso": "Altura inválida"}
    bw_calculado = (12 * i_x) / (h_total**3)
    return {
        "Tipo": "Retangular",
        "bw": round(bw_calculado, 2),
        "h": float(h_total)
    }


def desenhar_secao(dados: dict, exibir_cotas: bool = True,
                   h_laje: float = None, largura_colaborante: float = None,
                   gradiente: dict = None):
    """
    Gera o desenho técnico da seção transversal e, opcionalmente, o gradiente térmico.

    Melhorias v2.0:
      - Seção com hachura diagonal de concreto (estilo NBR).
      - Laje colaborante com cor e hachura distintas.
      - Marcador de CG profissional (círculo + cruz).
      - Cotas com linhas de extensão, setas controladas (mutation_scale=1)
        e caixas de texto com fundo.
      - Painel de gradiente com preenchimento suave e labels posicionados.

    figsize=(9.61, 4.91), dpi=100 – FIXO para QFrame 961x491 px.
    """
    # Propriedades geométricas
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

    # Figura (tamanho FIXO: 961x491 px)
    if gradiente:
        fig, (ax, ax_grad) = plt.subplots(
            1, 2, figsize=(9.61, 4.91), facecolor=COR_FUNDO, dpi=100,
            gridspec_kw={'width_ratios': [2, 1.2]}
        )
        ax_grad.set_facecolor(COR_FUNDO)
    else:
        fig, ax = plt.subplots(figsize=(9.61, 4.91), facecolor=COR_FUNDO, dpi=100)
        ax_grad = None

    ax.set_facecolor(COR_FUNDO)

    # Polígono da seção
    path_coords = []
    if tipo == "Retangular":
        b = dados.get("bw") or dados.get("b")
        h = res_base["h"]
        path_coords = [(-b/2, 0), (b/2, 0), (b/2, h), (-b/2, h)]
    elif tipo == "T":
        bw, h, bf, hf = dados["bw"], dados["h"], dados["bf"], dados["hf"]
        hw = h - hf
        path_coords = [
            (-bw/2, 0), (bw/2, 0), (bw/2, hw), (bf/2, hw),
            (bf/2, h),  (-bf/2, h), (-bf/2, hw), (-bw/2, hw)
        ]
    elif tipo == "I":
        bw, h    = dados["bw"], dados["h"]
        btf, hft = dados["btf"], dados["hft"]
        bfb, hfb = dados["bfb"], dados["hfb"]
        hw = h - hft - hfb
        path_coords = [
            (-bfb/2, 0),     (bfb/2, 0),     (bfb/2, hfb),     (bw/2, hfb),
            (bw/2, h-hft),   (btf/2, h-hft), (btf/2, h),       (-btf/2, h),
            (-btf/2, h-hft), (-bw/2, h-hft), (-bw/2, hfb),     (-bfb/2, hfb)
        ]

    # Seção com hachura de concreto
    ax.add_patch(patches.Polygon(
        path_coords, closed=True,
        facecolor=COR_CONCRETO, edgecolor=COR_BORDA, lw=1.4, zorder=2, hatch='////'
    ))

    # Laje colaborante
    if largura_colaborante is not None and h_laje is not None:
        ax.add_patch(patches.Rectangle(
            (-largura_colaborante / 2, h_base), largura_colaborante, h_laje,
            linewidth=1.4, edgecolor=COR_LAJE_ED,
            facecolor=COR_LAJE, zorder=2, alpha=0.80, hatch='..'
        ))

    # Marcador do CG (círculo + cruz)
    if exibir_cotas:
        _r = max(dados.get("bw", dados.get("b", 20)) * 0.04, 3.0)
        ax.add_patch(patches.Circle((0, ycg), _r,
            edgecolor=COR_CG, facecolor='none', lw=1.2, zorder=6))
        ax.plot([-_r*2.2, _r*2.2], [ycg, ycg], color=COR_CG, lw=0.8, zorder=6)
        ax.plot([0, 0], [ycg-_r*2.2, ycg+_r*2.2], color=COR_CG, lw=0.8, zorder=6)

    # Função de cotas com linhas de extensão e mutation_scale=1
    def draw_dim(p1, p2, label, offset=10, orientation='h'):
        TICK = max(2.0, offset * 0.20)
        if orientation == 'h':
            y_c = p1[1] + offset
            for xp in (p1[0], p2[0]):
                ax.plot([xp, xp], [y_c - TICK, y_c + TICK], color=COR_COTA, lw=0.6, zorder=3)
            ax.annotate('', xy=(p1[0], y_c), xytext=(p2[0], y_c),
                        arrowprops=dict(arrowstyle='<->', color=COR_COTA, lw=0.6, mutation_scale=1))
            ax.text((p1[0]+p2[0])/2, y_c + TICK*0.8,
                    f"{label}: {abs(p2[0]-p1[0]):.1f} cm",
                    color=COR_TXT, ha='center', va='bottom', fontsize=7,
                    bbox=dict(boxstyle='round,pad=0.15', facecolor=COR_FUNDO,
                              edgecolor=COR_COTA, linewidth=0.4, alpha=0.85))
        else:
            x_c = p1[0] + offset
            for yp in (p1[1], p2[1]):
                ax.plot([x_c - TICK, x_c + TICK], [yp, yp], color=COR_COTA, lw=0.6, zorder=3)
            ax.annotate('', xy=(x_c, p1[1]), xytext=(x_c, p2[1]),
                        arrowprops=dict(arrowstyle='<->', color=COR_COTA, lw=0.6, mutation_scale=1))
            ax.text(x_c + TICK*0.8, (p1[1]+p2[1])/2,
                    f"{label}: {abs(p2[1]-p1[1]):.1f} cm",
                    color=COR_TXT, ha='left', va='center', fontsize=7,
                    bbox=dict(boxstyle='round,pad=0.15', facecolor=COR_FUNDO,
                              edgecolor=COR_COTA, linewidth=0.4, alpha=0.85))

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

    # Limites da seção
    meia_largura = max(dados.get("bf", 0)/2, dados.get("btf", 0)/2,
                       dados.get("bfb", 0)/2, dados.get("bw", 0)/2, 25)
    meia_largura_laje = largura_colaborante / 2 if largura_colaborante else 0
    x_max = max(meia_largura, meia_largura_laje) + (20 if exibir_cotas else 0)
    y_min = -20
    y_max = h_total_comp + 20
    ax.set_xlim(-x_max, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect('equal')
    ax.axis('off')

    # Painel do gradiente térmico
    if ax_grad:
        h_grad = h_total_comp
        h1  = gradiente.get('h1', 0)
        h2  = gradiente.get('h2', 0)
        h3  = gradiente.get('h3', 0)
        dt1 = gradiente.get('deltat_1', 0)
        dt2 = gradiente.get('deltat_2', 0)
        dt3 = gradiente.get('deltat_3', 0)

        if h1 + h2 + h3 > h_grad:
            raise ValueError(
                f"Geometria inválida: soma de h1+h2+h3 ({h1+h2+h3:.2f}) "
                f"ultrapassa h_total ({h_grad:.2f})."
            )

        y_vals = [0, h3, h_grad - h1 - h2, h_grad - h1, h_grad]
        x_vals = [dt3, 0, 0, dt2, dt1]

        ax_grad.plot([0, 0], [0, h_grad], color=COR_BORDA, lw=1.2, zorder=3)
        ax_grad.plot(x_vals, y_vals, color=COR_BORDA, lw=1.5, zorder=4)
        ax_grad.fill_betweenx(y_vals, 0, x_vals, color='#FF8F00', alpha=0.55, zorder=2)
        ax_grad.axvline(0, color=COR_BORDA, lw=0.5, ls='--', alpha=0.3, zorder=1)

        max_dt   = max(abs(dt1), abs(dt2), abs(dt3), 1.0)
        off_text = max_dt * 0.12
        _lkw = dict(color=COR_TXT, va='center', fontsize=8,
                    bbox=dict(boxstyle='round,pad=0.18', facecolor=COR_FUNDO,
                              edgecolor='none', alpha=0.75))
        if dt1 != 0: ax_grad.text(dt1 + off_text, h_grad,      f"ΔT₁ = {dt1:.2f} °C", **_lkw)
        if dt2 != 0: ax_grad.text(dt2 + off_text, h_grad - h1, f"ΔT₂ = {dt2:.2f} °C", **_lkw)
        if dt3 != 0: ax_grad.text(dt3 + off_text, 0,           f"ΔT₃ = {dt3:.2f} °C", **_lkw)

        x_h_lines = -max_dt * 0.55
        x_h_total = -max_dt * 1.20
        for y_tick in y_vals:
            ax_grad.plot([x_h_lines, 0], [y_tick, y_tick],
                         color=COR_COTA, lw=0.7, linestyle='--', alpha=0.60)

        def draw_grad_h(y_top, y_bottom, x_pos, label):
            if abs(y_top - y_bottom) < 1e-3: return
            TICK_G = max_dt * 0.05
            for yp in (y_top, y_bottom):
                ax_grad.plot([x_pos - TICK_G, x_pos + TICK_G], [yp, yp],
                             color=COR_COTA, lw=0.6)
            ax_grad.annotate('', xy=(x_pos, y_top), xytext=(x_pos, y_bottom),
                             arrowprops=dict(arrowstyle='<->', color=COR_COTA,
                                             lw=0.7, mutation_scale=1))
            ax_grad.text(x_pos - TICK_G * 1.5, (y_top + y_bottom) / 2, label,
                         color=COR_TXT, ha='right', va='center', fontsize=7.5,
                         bbox=dict(boxstyle='round,pad=0.15', facecolor=COR_FUNDO,
                                   edgecolor='none', alpha=0.80))

        draw_grad_h(h_grad, h_grad - h1,           x_h_lines, f"h₁ = {h1:.2f}")
        draw_grad_h(h_grad - h1, h_grad - h1 - h2, x_h_lines, f"h₂ = {h2:.2f}")
        draw_grad_h(h3, 0,                          x_h_lines, f"h₃ = {h3:.2f}")
        draw_grad_h(h_grad, 0,                      x_h_total, f"h = {h_grad:.2f}")

        ax_grad.set_xlim(x_h_total * 1.5, max_dt * 2.2)
        ax_grad.set_ylim(y_min, y_max)
        ax_grad.axis('off')

    plt.tight_layout()
    return fig

def calcular_gradiente_equivalente(dados: dict, gradiente: dict, h_laje: float = None, largura_colaborante: float = None) -> tuple:
    """
    Calcula a variação linear equivalente de temperatura (Delta T_eq) integrando as fatias da seção
    segundo a ABNT NBR 7187. Retorna um dicionário com os resultados e uma string com o memorial de cálculo.
    """
    # 1. Obtém propriedades físicas da seção real
    res_secao = calcular_secao(dados, h_laje=h_laje, largura_colaborante=largura_colaborante)
    h_total = res_secao["h"]
    ycg = res_secao["ycg"]
    ix = res_secao["Ix"]
    h_base = dados.get("h", 0) # Altura apenas da longarina (sem laje)
    tipo = dados.get("Tipo")

    # Extração das variáveis do gradiente térmico
    h1, h2, h3 = gradiente.get('h1', 0), gradiente.get('h2', 0), gradiente.get('h3', 0)
    dt1, dt2, dt3 = gradiente.get('deltat_1', 0), gradiente.get('deltat_2', 0), gradiente.get('deltat_3', 0)

    # TRAVA DE SEGURANÇA: Geometria coerente
    if h1 + h2 + h3 > h_total:
        raise ValueError(f"Soma das alturas do gradiente ({h1+h2+h3}) excede h_total ({h_total}).")

    # 2. Função interna para descobrir a largura da seção B(Y) dada uma cota Y a partir da base
    def get_b(Y_cota):
        # Laje Colaborante
        if largura_colaborante is not None and h_laje is not None:
            if Y_cota > h_base: return largura_colaborante
        
        # Longarina
        if tipo == "Retangular":
            return dados.get("bw", dados.get("b", 0))
        elif tipo == "T":
            hw = h_base - dados["hf"]
            return dados["bw"] if Y_cota <= hw else dados["bf"]
        elif tipo == "I":
            hfb, hft = dados["hfb"], dados["hft"]
            hw = h_base - hft - hfb
            if Y_cota <= hfb: return dados["bfb"]
            elif Y_cota <= hfb + hw: return dados["bw"]
            else: return dados["btf"]
        return 0

    # 3. Função interna para descobrir a Temperatura T(Y) dada uma cota Y a partir da base
    def get_T(Y_cota):
        # Zona 1: Fundo (Varia de dt3 a 0)
        if Y_cota <= h3:
            return dt3 * (1 - Y_cota / h3) if h3 > 0 else 0
        # Zona 2: Miolo Neutro (Temperatura = 0)
        elif Y_cota <= h_total - h1 - h2:
            return 0
        # Zona 3: Transição topo (Varia de 0 a dt2)
        elif Y_cota <= h_total - h1:
            y_local = Y_cota - (h_total - h1 - h2)
            return dt2 * (y_local / h2) if h2 > 0 else dt2
        # Zona 4: Topo (Varia de dt2 a dt1)
        else:
            y_local = Y_cota - (h_total - h1)
            return dt2 + (dt1 - dt2) * (y_local / h1) if h1 > 0 else dt1

    # 4. Encontrar todos os pontos de "quebra" (descontinuidades geométricas ou térmicas)
    # Geometria
    pts_geo = [0, h_base]
    if tipo == "T": pts_geo.append(h_base - dados["hf"])
    elif tipo == "I": pts_geo.extend([dados["hfb"], h_base - dados["hft"]])
    if h_laje is not None: pts_geo.append(h_base + h_laje)
    
    # Gradiente Térmico
    pts_term = [0, h3, h_total - h1 - h2, h_total - h1, h_total]
    
    # Junta, filtra valores dentro do escopo, arredonda e tira duplicatas
    pontos = sorted(list(set(round(p, 5) for p in pts_geo + pts_term if 0 <= round(p, 5) <= round(h_total, 5))))

    # 5. Integração por Regra de Simpson (Exata para polinômios até 3º grau)
    # M_t = Integral [ b(Y) * T(Y) * (Y - ycg) * dY ]
    integral_Mt = 0
    linhas_memorial = [
        f"{'='*60}",
        f"MEMORIAL DE CÁLCULO - NBR 7187 (VARIAÇÃO NÃO UNIFORME DE TEMPERATURA)",
        f"{'='*60}",
        f"Propriedades da Seção:",
        f" - h_total: {h_total:.2f} cm",
        f" - ycg (da base): {ycg:.2f} cm",
        f" - Inércia (Ix): {ix:.2f} cm^4",
        f"\nIntegral de Momento Térmico M_t = ∫ b(y) * T(y) * y dy",
        f"Fatiamento da seção pelas descontinuidades geométricas e térmicas:"
    ]

    for i in range(len(pontos)-1):
        Ya = pontos[i]
        Yb = pontos[i+1]
        if Yb - Ya <= 1e-4: continue # Pula fatias de espessura nula

        # Dentro do trecho, a largura b(Y) é constante. Pegamos no ponto médio para evitar falsas quebras de contorno.
        Y_mid = (Ya + Yb) / 2
        b_val = get_b(Y_mid)

        # Função a ser integrada: f(Y) = b_val * T(Y) * y_local
        def f(Y):
            y_local = Y - ycg # Distância real ao CG
            return b_val * get_T(Y) * y_local

        # Regra de Simpson: Integral = (Largura / 6) * [f(inicio) + 4f(meio) + f(fim)]
        val_integral = ((Yb - Ya) / 6.0) * (f(Ya) + 4*f(Y_mid) + f(Yb))
        integral_Mt += val_integral

        linhas_memorial.append(
            f" > Trecho [{Ya:6.2f} a {Yb:6.2f} cm] | Largura b={b_val:6.2f} | ΔM_t = {val_integral:10.2f}"
        )

    # 6. Cálculo das temperaturas equivalentes nas fibras extremas
    y_sup = h_total - ycg
    y_inf = -ycg
    
    T_sup = (y_sup / ix) * integral_Mt
    T_inf = (y_inf / ix) * integral_Mt
    delta_T_eq = T_sup - T_inf

    linhas_memorial.extend([
        f"{'-'*60}",
        f"Resultados da Integração:",
        f" - M_t Total: {integral_Mt:.2f}",
        f" - T_sup_eq (y_s = {y_sup:.2f} cm): {T_sup:.2f} °C",
        f" - T_inf_eq (y_i = {y_inf:.2f} cm): {T_inf:.2f} °C",
        f" - Gradiente Térmico Linear Equivalente (ΔT_eq): {delta_T_eq:.2f} °C",
        f"{'='*60}"
    ])

    resultados = {
        "M_t": integral_Mt,
        "T_sup_eq": T_sup,
        "T_inf_eq": T_inf,
        "Delta_T_eq": delta_T_eq
    }

    return resultados, "\n".join(linhas_memorial)


def gerar_html_gradiente_termico(resultados, memorial_texto, ativo=True):
    """
    Gera o HTML profissional para o memorial de cálculo do gradiente térmico.
    Converte variáveis com '_' em índices e renderiza a fórmula da integral.
    Se ativo=False, todas as cores destacadas tornam-se cinza.
    """
    # Cores (Paleta Quente)
    if ativo:
        c_mt = "#f39c12"      # Laranja para Momento Térmico
        c_temp = "#f1c40f"    # Amarelo para Temperaturas
        c_final = "#e74c3c"   # Vermelho para o Resultado Final
    else:
        c_mt = "#888888"
        c_temp = "#888888"
        c_final = "#888888"

    # Função auxiliar para converter var_nome em var<sub>nome</sub>
    def formatar_indices(texto):
        # Procura padrões como M_t, y_cg, h_total e transforma o que vem após o _ em subscrito
        return re.sub(r'_(\w+)', r'<sub>\1</sub>', texto)

    # Extração e formatação dos dados
    mt_total = resultados.get("M_t", 0)
    t_sup = resultados.get("T_sup_eq", 0)
    t_inf = resultados.get("T_inf_eq", 0)
    delta_t = resultados.get("Delta_T_eq", 0)

    # Processamento das linhas de fatiamento
    linhas = memorial_texto.split('\n')
    fatias_html = ""
    for linha in linhas:
        if "> Trecho" in linha:
            # Formata a linha e substitui o '_' por índice
            linha_formatada = formatar_indices(linha.replace("> ", ""))
            fatias_html += f"<div style='font-family: \"Courier New\", monospace; font-size: 10.5pt; margin-left: 15px; color: #ecf0f1;'>&bull; {linha_formatada}</div>"

    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 13pt; color: white; line-height: 1.5;'>
        
        <div style='border-left: 5px solid {c_final}; padding-left: 15px; margin-bottom: 20px;'>
            <b style='font-size: 15pt; text-transform: uppercase;'>Memorial de Cálculo: Gradiente Térmico</b><br>
            <span style='font-size: 10pt; color: #bdc3c7;'>Referência Normativa: ABNT NBR 7187</span>
        </div>

        <div style='background: rgba(255,255,255,0.03); padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 20px; border: 1px dashed #555;'>
            <span style='font-style: italic; font-size: 14pt;'>
                M<sub>t</sub> = &int; b(y) &middot; T(y) &middot; (y - y<sub>cg</sub>) dy
            </span>
        </div>

        <div style='margin-bottom: 20px;'>
            <b style='color: {c_mt};'>Integração por Fatias Geométricas:</b>
            <div style='margin-top: 10px;'>
                {fatias_html}
            </div>
        </div>

        <div style='border: 1px solid #444; padding: 15px; border-radius: 10px; background: linear-gradient(145deg, #2c3e50, #1a1a1a);'>
            <table style='width: 100%; border-collapse: collapse;'>
                <tr>
                    <td style='padding: 5px;'>Momento Térmico Total (<b>M<sub>t</sub></b>):</td>
                    <td style='text-align: right; color: {c_mt}; font-weight: bold;'>{mt_total:.2f} cm&sup2;&middot;&deg;C</td>
                </tr>
                <tr>
                    <td style='padding: 5px;'>Temperatura Equivalente Superior (<b>T<sub>sup,eq</sub></b>):</td>
                    <td style='text-align: right; color: {c_temp};'>{t_sup:.2f} &deg;C</td>
                </tr>
                <tr>
                    <td style='padding: 5px;'>Temperatura Equivalente Inferior (<b>T<sub>inf,eq</sub></b>):</td>
                    <td style='text-align: right; color: {c_temp};'>{t_inf:.2f} &deg;C</td>
                </tr>
                <tr style='border-top: 1px solid #555;'>
                    <td style='padding: 10px 5px 0 5px; font-size: 14pt;'><b>&Delta;T<sub>eq</sub> Linear Final:</b></td>
                    <td style='padding: 10px 5px 0 5px; text-align: right; color: {c_final}; font-size: 16pt; font-weight: bold;'>
                        {delta_t:.2f} &deg;C
                    </td>
                </tr>
            </table>
        </div>

    </body>
    </html>
    """
    return html


def gerar_html_parametros_gradiente(h_total, espessura_media, gradiente_ponte):
    """
    Gera o HTML visual para a entrada de dados do gradiente térmico.
    A seta agora utiliza um caractere Unicode de peça única para evitar desalinhamento.
    """
    # Extração dos dados
    h1, h2, h3 = gradiente_ponte.get('h1', 0), gradiente_ponte.get('h2', 0), gradiente_ponte.get('h3', 0)
    dt1, dt2, dt3 = gradiente_ponte.get('deltat_1', 0), gradiente_ponte.get('deltat_2', 0), gradiente_ponte.get('deltat_3', 0)

    # Cores
    c_destaque = "#f1c40f" 
    c_norma = "#2ecc71"    # Verde conforme solicitado

    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 13pt; color: white; background-color: transparent;'>
        <table style='border-collapse: collapse; width: auto;'>
            <tr>
                <td style='padding-right: 10px; vertical-align: middle;'>
                    <div style='white-space: nowrap; margin-bottom: 8px;'>
                        Altura da superestrutura (h = h<sub>longarina</sub> + h<sub>laje</sub>) = <b>{h_total:.2f} cm</b>
                    </div>
                    <div style='white-space: nowrap;'>
                        Espessura média do revestimento (h<sub>revestimento</sub>) = <b>{espessura_media:.2f} cm</b>
                    </div>
                </td>

                <td style='font-size: 45pt; font-weight: 100; vertical-align: middle; padding: 0 5px; color: #bdc3c7;'>
                    &#125; 
                </td>

                <td style='text-align: center; vertical-align: middle; padding: 0 15px;'>
                    <div style='white-space: nowrap; font-size: 12pt; color: {c_norma}; font-weight: bold; display: flex; align-items: center;'>
                        <span>NBR 7187:2021 &sect; 7.3.8.2.3</span>
                        <span style='font-size: 20pt; margin-left: 8px; line-height: 0;'>&#10230;</span>
                    </div>
                </td>

                <td style='padding-left: 10px; vertical-align: middle; border-left: 1px solid #444;'>
                    <div style='white-space: nowrap; margin-bottom: 5px;'>
                        h<sub>1</sub> = {h1:.1f} cm | <span style='color: {c_destaque};'>&Delta;T<sub>1</sub> = {dt1:.1f} &deg;C</span>
                    </div>
                    <div style='white-space: nowrap; margin-bottom: 5px;'>
                        h<sub>2</sub> = {h2:.1f} cm | <span style='color: {c_destaque};'>&Delta;T<sub>2</sub> = {dt2:.1f} &deg;C</span>
                    </div>
                    <div style='white-space: nowrap;'>
                        h<sub>3</sub> = {h3:.1f} cm | <span style='color: {c_destaque};'>&Delta;T<sub>3</sub> = {dt3:.1f} &deg;C</span>
                    </div>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    return html


def obter_gradiente_ponte(h_total_cm, espessura_revest_cm):
    """
    Calcula os parâmetros h1, h2, h3 e deltat1, 2, 3 conforme NBR 7187:2021 (Tabela 4).
    As entradas são em cm, e o retorno é um dicionário compatível com sua estrutura.
    """
    # 1. Conversão para metros (unidade base da norma para os limites)
    h = h_total_cm / 100.0
    e_rev = espessura_revest_cm / 100.0
    e_rev_mm = espessura_revest_cm * 10.0 # Tabela 4 usa mm

    # 2. Cálculo das alturas do gradiente (NBR 7187 - 7.3.8.2.3)
    # h1: 0.3h limitado a 0.15m
    h1 = min(0.3 * h, 0.15) 
    
    # h2: 0.3h entre 0.10m e 0.25m
    h2 = max(0.10, min(0.3 * h, 0.25))
    
    # h3: 0.3h limitado a (0.10m + revest) e ao que sobra da seção
    h3_limite_rev = 0.10 + e_rev
    h3 = min(0.3 * h, h3_limite_rev, h - h1 - h2) 

    # 3. Dados da Tabela 4 (Alturas: 0.2, 0.4, 0.6, >=0.8 | Espessuras: 0, 50, 100, 150, 200 mm)
    # Estrutura: tabela_4[altura_m][espessura_mm] = (dT1, dT2, dT3)
    tabela_4 = {
        0.2: {0: (12.0, 5.0, 0.1), 50: (13.2, 4.9, 0.3), 100: (8.5, 3.5, 0.5), 150: (5.6, 2.5, 0.2), 200: (3.7, 2.0, 0.5)},
        0.4: {0: (15.2, 4.4, 1.2), 50: (17.2, 4.6, 1.4), 100: (12.0, 3.0, 1.5), 150: (8.5, 2.0, 1.2), 200: (6.2, 1.3, 1.0)},
        0.6: {0: (15.2, 4.0, 1.4), 50: (17.6, 4.0, 1.8), 100: (13.0, 3.0, 2.0), 150: (9.7, 2.2, 1.7), 200: (7.2, 1.5, 1.5)},
        0.8: {0: (15.4, 4.0, 2.0), 50: (17.8, 4.0, 2.1), 100: (13.5, 3.0, 2.5), 150: (10.0, 2.5, 2.0), 200: (7.5, 2.1, 1.5)}
    }

    def interpolar_1d(x, x0, x1, y0, y1):
        if x0 == x1: return y0
        return y0 + (x - x0) * (y1 - y0) / (x1 - x0)

    def obter_valores_por_espessura(h_ref, e_alvo):
        espessuras = sorted(tabela_4[h_ref].keys())
        e_inf = max([e for e in espessuras if e <= e_alvo] or [0])
        e_sup = min([e for e in espessuras if e >= e_alvo] or [200])
        
        v_inf = tabela_4[h_ref][e_inf]
        v_sup = tabela_4[h_ref][e_sup]
        
        return tuple(interpolar_1d(e_alvo, e_inf, e_sup, v_inf[i], v_sup[i]) for i in range(3))

    # 4. Interpolação Final (Bilinear: entre alturas e espessuras)
    alturas = sorted(tabela_4.keys())
    h_alvo = max(0.2, min(h, 0.8)) # Clampa h entre os limites da tabela
    e_alvo = max(0, min(e_rev_mm, 200))

    h_inf = max([a for a in alturas if a <= h_alvo] or [0.2])
    h_sup = min([a for a in alturas if a >= h_alvo] or [0.8])

    val_inf = obter_valores_por_espessura(h_inf, e_alvo)
    val_sup = obter_valores_por_espessura(h_sup, e_alvo)

    dt1, dt2, dt3 = (interpolar_1d(h_alvo, h_inf, h_sup, val_inf[i], val_sup[i]) for i in range(3))

    return {
        "h1": h1 * 100, # Retorna em cm
        "h2": h2 * 100, 
        "h3": h3 * 100,  
        "deltat_1": round(dt1, 2), 
        "deltat_2": round(dt2, 2), 
        "deltat_3": round(dt3, 2)
    }


def gerar_memorial_gradiente_ponte(h_total_cm: float, espessura_revest_cm: float) -> str:
    """
    Gera um memorial de cálculo HTML completo para o gradiente térmico de uma ponte.
    Exibe passo a passo: cálculo de h1, h2, h3 com seus limites normativos e a
    interpolação bilinear na Tabela 4 da NBR 7187:2021.

    Parâmetros:
        h_total_cm         : Altura total da superestrutura [cm] (longarina + laje).
        espessura_revest_cm: Espessura do revestimento/pavimento [cm].

    Retorna:
        str: String HTML completa pronta para exibição.
    """
    # ── Recalcular passos intermediários para o memorial ─────────────────────
    h      = h_total_cm      / 100.0   # metros
    e_rev  = espessura_revest_cm / 100.0   # metros
    e_rev_mm = espessura_revest_cm * 10.0  # mm (Tabela 4 usa mm)

    # h1: 0.3h com máximo de 0.15 m
    h1_raw     = 0.3 * h
    h1         = min(h1_raw, 0.15)
    h1_limitado = h1_raw > 0.15

    # h2: 0.3h limitado ao intervalo [0.10 m ; 0.25 m]
    h2_raw    = 0.3 * h
    h2        = max(0.10, min(h2_raw, 0.25))
    h2_lim_inf = h2_raw < 0.10
    h2_lim_sup = h2_raw > 0.25

    # h3: 0.3h limitado por (0.10 + e_rev) e pela altura restante
    h3_raw       = 0.3 * h
    h3_lim_rev   = 0.10 + e_rev
    h3_lim_sec   = h - h1 - h2
    h3           = min(h3_raw, h3_lim_rev, h3_lim_sec)
    if   abs(h3 - h3_lim_sec) < 1e-9:  h3_fator = "H − h₁ − h₂  (altura restante da seção)"
    elif abs(h3 - h3_lim_rev) < 1e-9:  h3_fator = "0,10 + e_rev  (limite do revestimento)"
    else:                               h3_fator = "0,3 × H  (sem limitação ativa)"

    # ── Tabela 4 NBR 7187:2021 (idêntica à usada em obter_gradiente_ponte) ───
    tabela_4 = {
        0.2: {0: (12.0,5.0,0.1), 50: (13.2,4.9,0.3), 100: (8.5,3.5,0.5), 150: (5.6,2.5,0.2), 200: (3.7,2.0,0.5)},
        0.4: {0: (15.2,4.4,1.2), 50: (17.2,4.6,1.4), 100: (12.0,3.0,1.5), 150: (8.5,2.0,1.2), 200: (6.2,1.3,1.0)},
        0.6: {0: (15.2,4.0,1.4), 50: (17.6,4.0,1.8), 100: (13.0,3.0,2.0), 150: (9.7,2.2,1.7), 200: (7.2,1.5,1.5)},
        0.8: {0: (15.4,4.0,2.0), 50: (17.8,4.0,2.1), 100: (13.5,3.0,2.5), 150: (10.0,2.5,2.0), 200: (7.5,2.1,1.5)}
    }
    alturas   = sorted(tabela_4.keys())
    h_alvo    = max(0.2, min(h, 0.8))
    e_alvo    = max(0.0, min(e_rev_mm, 200.0))
    h_clamped = (h < 0.2 or h > 0.8)
    e_clamped = (e_rev_mm < 0 or e_rev_mm > 200)

    h_inf = max([a for a in alturas if a <= h_alvo] or [0.2])
    h_sup = min([a for a in alturas if a >= h_alvo] or [0.8])
    espessuras = sorted(tabela_4[h_inf].keys())
    e_inf = max([e for e in espessuras if e <= e_alvo] or [0])
    e_sup = min([e for e in espessuras if e >= e_alvo] or [200])

    v_pp = tabela_4[h_inf][e_inf]   # P₁ (h_inf, e_inf)
    v_pq = tabela_4[h_inf][e_sup]   # P₂ (h_inf, e_sup)
    v_qp = tabela_4[h_sup][e_inf]   # P₃ (h_sup, e_inf)
    v_qq = tabela_4[h_sup][e_sup]   # P₄ (h_sup, e_sup)

    # ── Resultados finais (via função existente) ──────────────────────────────
    res  = obter_gradiente_ponte(h_total_cm, espessura_revest_cm)
    dt1, dt2, dt3   = res["deltat_1"], res["deltat_2"], res["deltat_3"]
    h1_cm, h2_cm, h3_cm = res["h1"], res["h2"], res["h3"]

    # ── Auxiliares de formatação ──────────────────────────────────────────────
    def _lim_badge(ativo, texto):
        cls = "badge-warn" if ativo else "badge-ok"
        msg = texto if ativo else "✓ sem limite ativo"
        return f'<span class="{cls}">{msg}</span>'

    def _highlight_row(cond):
        return ' class="highlight"' if cond else ""

    h2_status = ("⚠ Limitado ao mínimo de 0,10 m" if h2_lim_inf else
                 ("⚠ Limitado ao máximo de 0,25 m" if h2_lim_sup else ""))

    # ── Geração HTML ─────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
        font-family: 'Segoe UI', Tahoma, sans-serif;
        background-color: #0f172a; color: #e2e8f0;
        padding: 20px; font-size: 14px; line-height: 1.6;
    }}
    .container {{
        max-width: 1000px; margin: 0 auto;
        background: #1e293b; border-radius: 12px;
        overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    }}
    .header {{
        background: linear-gradient(135deg, #7c2d12 0%, #c2410c 50%, #9a3412 100%);
        padding: 28px; text-align: center; color: white;
    }}
    .header h1 {{ margin: 0 0 6px 0; font-size: 1.55em; letter-spacing: 0.5px; }}
    .header p  {{ margin: 0; opacity: 0.8; font-size: 0.92em; }}
    .content   {{ padding: 28px; }}
    .section {{
        margin-bottom: 28px;
        border-left: 4px solid #f97316;
        padding: 18px 18px 18px 20px;
        background: rgba(30,20,10,0.5);
        border-radius: 0 10px 10px 0;
    }}
    .section-title {{
        font-size: 1.15em; font-weight: bold; color: #fdba74;
        margin-bottom: 14px; border-bottom: 1px solid #334155; padding-bottom: 8px;
    }}
    .sub-title {{ color: #fed7aa; font-weight: bold; margin: 18px 0 8px 0; font-size: 0.98em; }}
    .info-box {{
        background: rgba(15,23,42,0.6); border-radius: 6px;
        padding: 10px 14px; margin-bottom: 12px;
        border-left: 3px solid #f97316;
    }}
    .formula-eq {{
        background: #0f172a; border-left: 3px solid #fbbf24;
        padding: 10px 14px; font-family: 'Courier New', monospace;
        color: #fef3c7; font-size: 0.93em; margin: 8px 0;
        border-radius: 0 6px 6px 0; white-space: pre-wrap;
    }}
    .resultado-destaque {{
        background: #431407; border: 1px solid #f97316;
        border-radius: 6px; padding: 8px 16px;
        font-size: 1.05em; font-weight: bold; color: #fdba74;
        margin: 10px 0; display: inline-block;
    }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
    .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }}
    table   {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 0.88em; }}
    th      {{ background: #431407; color: #fdba74; padding: 7px 10px; text-align: center; border-bottom: 2px solid #f97316; }}
    td      {{ padding: 6px 10px; border-bottom: 1px solid #1e293b; text-align: center; }}
    tr:hover td {{ background: rgba(249,115,22,0.08); }}
    td:first-child {{ text-align: left; color: #94a3b8; }}
    .badge-ok   {{ background:#166534; color:#4ade80; padding:2px 10px; border-radius:12px; font-size:0.85em; font-weight:bold; border:1px solid #16a34a; }}
    .badge-warn {{ background:#78350f; color:#fbbf24; padding:2px 10px; border-radius:12px; font-size:0.85em; font-weight:bold; border:1px solid #f59e0b; }}
    .badge-ref  {{ background:#1e3a5f; color:#93c5fd; padding:2px 10px; border-radius:12px; font-size:0.85em; font-weight:bold; border:1px solid #3b82f6; }}
    .highlight td {{ background: rgba(249,115,22,0.15) !important; font-weight: bold; color: #fdba74; }}
    .card {{
        background: rgba(15,23,42,0.7); border-radius: 10px;
        padding: 18px; border: 1px solid #374151; text-align: center;
    }}
    .card-val   {{ font-size: 1.8em; font-weight: bold; color: #fb923c; margin: 8px 0 4px 0; }}
    .card-label {{ font-size: 0.85em; color: #9ca3af; }}
    .card-temp  {{ color: #fb923c; font-size: 1.2em; font-weight: bold; }}
    .footer     {{ background: #0f172a; padding: 14px; text-align: center; color: #475569; font-size: 0.82em; }}
</style>
</head>
<body>
<div class="container">

    <div class="header">
        <h1>🌡️ Memorial de Cálculo – Gradiente Térmico de Ponte</h1>
        <p>Variação Não Uniforme de Temperatura · ABNT NBR 7187:2021 · Tabela 4 · Interpolação Bilinear</p>
    </div>

    <div class="content">

        <!-- ═══════════════════════════════════════════════════════════════ -->
        <!-- SEÇÃO 1 – DADOS DE ENTRADA                                     -->
        <!-- ═══════════════════════════════════════════════════════════════ -->
        <div class="section">
            <div class="section-title">📌 SEÇÃO 1 – Dados de Entrada</div>
            <div class="grid-2">
                <div>
                    <p class="sub-title">1.1 Geometria da Superestrutura</p>
                    <table>
                        <tr>
                            <td>Altura total (H = h<sub>longarina</sub> + h<sub>laje</sub>)</td>
                            <td><strong>{h_total_cm:.2f} cm &nbsp;=&nbsp; {h:.4f} m</strong></td>
                        </tr>
                        <tr>
                            <td>Espessura do revestimento (e<sub>rev</sub>)</td>
                            <td><strong>{espessura_revest_cm:.2f} cm &nbsp;=&nbsp; {e_rev:.4f} m &nbsp;=&nbsp; {e_rev_mm:.1f} mm</strong></td>
                        </tr>
                    </table>
                </div>
                <div>
                    <p class="sub-title">1.2 Referência Normativa</p>
                    <div class="info-box">
                        <p><strong>ABNT NBR 7187:2021</strong></p>
                        <p style="margin-top:6px; color:#94a3b8;">
                            § 7.3.8.2.3 – Variação não uniforme de temperatura<br>
                            Os parâmetros h₁, h₂, h₃ e ΔT₁, ΔT₂, ΔT₃ definem a
                            distribuição de temperatura ao longo da seção transversal.
                        </p>
                    </div>
                </div>
            </div>
        </div>

        <!-- ═══════════════════════════════════════════════════════════════ -->
        <!-- SEÇÃO 2 – ALTURAS DO GRADIENTE                                 -->
        <!-- ═══════════════════════════════════════════════════════════════ -->
        <div class="section">
            <div class="section-title">📐 SEÇÃO 2 – Cálculo das Alturas do Gradiente (§ 7.3.8.2.3)</div>

            <div class="info-box">
                As alturas h₁, h₂, h₃ são frações de 0,3H, cada qual sujeita a
                limites mínimos e máximos conforme indicado abaixo.
            </div>

            <!-- h1 -->
            <p class="sub-title">► 2.1  h₁ – Zona do Topo (ΔT₁ → ΔT₂)</p>
            <p class="formula-eq">Fórmula : h₁ = 0,3 × H,  com máximo de 0,15 m

h₁_bruto = 0,3 × {h:.4f} m = {h1_raw:.4f} m = {h1_raw*100:.2f} cm
Limite   : h₁ ≤ 0,15 m
h₁       = min({h1_raw:.4f} m ; 0,15 m) = {h1:.4f} m = <strong>{h1*100:.2f} cm</strong></p>
            {_lim_badge(h1_limitado, "⚠ Limitado a 0,15 m (máximo)")}
            <div class="resultado-destaque">h₁ = {h1_cm:.2f} cm</div>

            <!-- h2 -->
            <p class="sub-title">► 2.2  h₂ – Zona de Transição (ΔT₂ → 0)</p>
            <p class="formula-eq">Fórmula : h₂ = 0,3 × H,  com intervalo [0,10 m ; 0,25 m]

h₂_bruto = 0,3 × {h:.4f} m = {h2_raw:.4f} m = {h2_raw*100:.2f} cm
Limites  : h₂ ∈ [0,10 m ; 0,25 m]
h₂       = max(0,10 ; min({h2_raw:.4f} ; 0,25)) = {h2:.4f} m = <strong>{h2*100:.2f} cm</strong>
{('Limite ativo: mínimo de 0,10 m' if h2_lim_inf else ('Limite ativo: máximo de 0,25 m' if h2_lim_sup else 'Sem limite ativo: 0,3H ∈ [0,10 m ; 0,25 m]'))}</p>
            {_lim_badge(h2_lim_inf or h2_lim_sup, h2_status)}
            <div class="resultado-destaque">h₂ = {h2_cm:.2f} cm</div>

            <!-- h3 -->
            <p class="sub-title">► 2.3  h₃ – Zona da Base (0 → ΔT₃)</p>
            <p class="formula-eq">Fórmula : h₃ = 0,3 × H,  limitado pelo revestimento e pela altura restante

h₃_bruto           = 0,3 × {h:.4f} m = {h3_raw:.4f} m = {h3_raw*100:.2f} cm
Limite revestimento = 0,10 + e_rev = 0,10 + {e_rev:.4f} m = {h3_lim_rev:.4f} m = {h3_lim_rev*100:.2f} cm
Limite da seção    = H − h₁ − h₂ = {h:.4f} − {h1:.4f} − {h2:.4f} = {h3_lim_sec:.4f} m = {h3_lim_sec*100:.2f} cm
h₃                 = min({h3_raw:.4f} ; {h3_lim_rev:.4f} ; {h3_lim_sec:.4f}) = {h3:.4f} m = <strong>{h3*100:.2f} cm</strong>
Fator limitante ativo: {h3_fator}</p>
            <div class="resultado-destaque">h₃ = {h3_cm:.2f} cm</div>

            <!-- Verificação geométrica -->
            <p class="sub-title">► 2.4  Verificação Geométrica</p>
            <table>
                <thead><tr><th>Zona</th><th>Altura (m)</th><th>Altura (cm)</th><th>Temperatura</th></tr></thead>
                <tbody>
                    <tr><td>Topo – h₁</td><td>{h1:.4f}</td><td>{h1_cm:.2f}</td><td>ΔT₁ → ΔT₂</td></tr>
                    <tr><td>Transição – h₂</td><td>{h2:.4f}</td><td>{h2_cm:.2f}</td><td>ΔT₂ → 0</td></tr>
                    <tr><td>Zona neutra</td><td>{h - h1 - h2 - h3:.4f}</td><td>{(h - h1 - h2 - h3)*100:.2f}</td><td>T = 0</td></tr>
                    <tr><td>Base – h₃</td><td>{h3:.4f}</td><td>{h3_cm:.2f}</td><td>0 → ΔT₃</td></tr>
                    <tr style="border-top:2px solid #f97316;"><td><strong>TOTAL</strong></td><td><strong>{h:.4f}</strong></td><td><strong>{h_total_cm:.2f}</strong></td><td>–</td></tr>
                </tbody>
            </table>
        </div>

        <!-- ═══════════════════════════════════════════════════════════════ -->
        <!-- SEÇÃO 3 – INTERPOLAÇÃO NA TABELA 4                             -->
        <!-- ═══════════════════════════════════════════════════════════════ -->
        <div class="section">
            <div class="section-title">📊 SEÇÃO 3 – Temperaturas via Tabela 4 (NBR 7187:2021)</div>

            <div class="info-box">
                ΔT₁, ΔT₂, ΔT₃ são obtidos por <strong>interpolação bilinear</strong>
                na Tabela 4 da norma, em função de H (m) e e<sub>rev</sub> (mm).
                Os valores interpolados são os máximos de aquecimento do topo.
            </div>

            <p class="sub-title">► 3.1  Parâmetros de Interpolação</p>
            <table>
                <tr>
                    <td>H efetivo (fixado em [0,2 m ; 0,8 m])</td>
                    <td><strong>{h_alvo:.3f} m{' &nbsp;<span class="badge-warn">⚠ clamped</span>' if h_clamped else ''}</strong></td>
                </tr>
                <tr>
                    <td>e<sub>rev</sub> efetivo (fixado em [0 ; 200 mm])</td>
                    <td><strong>{e_alvo:.1f} mm{' &nbsp;<span class="badge-warn">⚠ clamped</span>' if e_clamped else ''}</strong></td>
                </tr>
                <tr>
                    <td>Linhas de H utilizadas (interpolação em H)</td>
                    <td><strong>h_inf = {h_inf:.1f} m &nbsp;|&nbsp; h_sup = {h_sup:.1f} m</strong></td>
                </tr>
                <tr>
                    <td>Colunas de espessura utilizadas (interpolação em e)</td>
                    <td><strong>e_inf = {e_inf:.0f} mm &nbsp;|&nbsp; e_sup = {e_sup:.0f} mm</strong></td>
                </tr>
            </table>

            <p class="sub-title">► 3.2  Pontos de Referência da Tabela 4</p>
            <table>
                <thead>
                    <tr>
                        <th>Ponto</th><th>H (m)</th><th>e<sub>rev</sub> (mm)</th>
                        <th>ΔT₁ (°C)</th><th>ΔT₂ (°C)</th><th>ΔT₃ (°C)</th>
                    </tr>
                </thead>
                <tbody>
                    <tr{_highlight_row(True)}><td><span class="badge-ref">P₁</span></td><td>{h_inf:.1f}</td><td>{e_inf:.0f}</td><td>{v_pp[0]:.1f}</td><td>{v_pp[1]:.1f}</td><td>{v_pp[2]:.1f}</td></tr>
                    <tr{_highlight_row(e_inf != e_sup)}><td><span class="badge-ref">P₂</span></td><td>{h_inf:.1f}</td><td>{e_sup:.0f}</td><td>{v_pq[0]:.1f}</td><td>{v_pq[1]:.1f}</td><td>{v_pq[2]:.1f}</td></tr>
                    <tr{_highlight_row(h_inf != h_sup)}><td><span class="badge-ref">P₃</span></td><td>{h_sup:.1f}</td><td>{e_inf:.0f}</td><td>{v_qp[0]:.1f}</td><td>{v_qp[1]:.1f}</td><td>{v_qp[2]:.1f}</td></tr>
                    <tr{_highlight_row(h_inf != h_sup and e_inf != e_sup)}><td><span class="badge-ref">P₄</span></td><td>{h_sup:.1f}</td><td>{e_sup:.0f}</td><td>{v_qq[0]:.1f}</td><td>{v_qq[1]:.1f}</td><td>{v_qq[2]:.1f}</td></tr>
                </tbody>
            </table>
            <p style="color:#94a3b8; font-size:0.88em; margin-top:4px;">
                Linhas destacadas são os pontos efetivamente usados na interpolação bilinear.
            </p>

            <p class="sub-title">► 3.3  Resultado da Interpolação Bilinear</p>
            <p class="formula-eq">H_alvo = {h_alvo:.3f} m   →   interpolação entre H = {h_inf:.1f} m e H = {h_sup:.1f} m
e_alvo = {e_alvo:.1f} mm  →   interpolação entre e = {e_inf:.0f} mm e e = {e_sup:.0f} mm

Resultado:
  ΔT₁ = {dt1:.2f} °C   (temperatura máxima no topo)
  ΔT₂ = {dt2:.2f} °C   (temperatura na base de h₁)
  ΔT₃ = {dt3:.2f} °C   (temperatura máxima na base)</p>
        </div>

        <!-- ═══════════════════════════════════════════════════════════════ -->
        <!-- SEÇÃO 4 – RESULTADOS FINAIS                                    -->
        <!-- ═══════════════════════════════════════════════════════════════ -->
        <div class="section">
            <div class="section-title">✅ SEÇÃO 4 – Resultados Finais do Gradiente Térmico</div>

            <p class="sub-title">► Tabela Resumo dos Parâmetros</p>
            <table>
                <thead>
                    <tr>
                        <th>Zona</th>
                        <th>Altura h (cm)</th>
                        <th>ΔT (°C)</th>
                        <th>Descrição do trecho</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td style="color:#fdba74; font-weight:bold;">Zona 1 – Topo</td>
                        <td><strong>{h1_cm:.2f}</strong></td>
                        <td><strong>{dt1:.2f}</strong></td>
                        <td style="color:#94a3b8; text-align:left;">Temperatura varia de ΔT₁ (topo) a ΔT₂ (base de h₁)</td>
                    </tr>
                    <tr>
                        <td style="color:#fdba74; font-weight:bold;">Zona 2 – Transição</td>
                        <td><strong>{h2_cm:.2f}</strong></td>
                        <td><strong>{dt2:.2f}</strong></td>
                        <td style="color:#94a3b8; text-align:left;">Temperatura varia de ΔT₂ linearmente até zero</td>
                    </tr>
                    <tr>
                        <td style="color:#94a3b8;">Zona neutra</td>
                        <td>{(h - h1 - h2 - h3)*100:.2f}</td>
                        <td>0,00</td>
                        <td style="color:#94a3b8; text-align:left;">Miolo da seção sem variação térmica</td>
                    </tr>
                    <tr>
                        <td style="color:#fdba74; font-weight:bold;">Zona 3 – Base</td>
                        <td><strong>{h3_cm:.2f}</strong></td>
                        <td><strong>{dt3:.2f}</strong></td>
                        <td style="color:#94a3b8; text-align:left;">Temperatura varia de zero até ΔT₃ (fundo)</td>
                    </tr>
                </tbody>
            </table>

            <p class="sub-title" style="margin-top:22px;">► Cards de Resultado – Entrada para calcular_gradiente_equivalente</p>
            <div class="grid-3">
                <div class="card">
                    <div class="card-label">h₁ &nbsp;|&nbsp; ΔT₁</div>
                    <div class="card-val">{h1_cm:.2f} cm</div>
                    <div class="card-temp">{dt1:.2f} °C</div>
                </div>
                <div class="card">
                    <div class="card-label">h₂ &nbsp;|&nbsp; ΔT₂</div>
                    <div class="card-val">{h2_cm:.2f} cm</div>
                    <div class="card-temp">{dt2:.2f} °C</div>
                </div>
                <div class="card">
                    <div class="card-label">h₃ &nbsp;|&nbsp; ΔT₃</div>
                    <div class="card-val">{h3_cm:.2f} cm</div>
                    <div class="card-temp">{dt3:.2f} °C</div>
                </div>
            </div>

            <div class="info-box" style="margin-top:20px;">
                <p>Para calcular o gradiente térmico linear equivalente (ΔT_eq) para uso em análise
                   estrutural, passe estes parâmetros para
                   <code>calcular_gradiente_equivalente()</code> juntamente com as propriedades
                   geométricas da seção transversal.</p>
            </div>
        </div>

    </div><!-- fim .content -->

    <div class="footer">
        Memorial de Cálculo gerado automaticamente &middot;
        Gradiente Térmico – ABNT NBR 7187:2021 &middot;
        Interpolação Bilinear na Tabela 4
    </div>

</div><!-- fim .container -->
</body>
</html>"""

    return html


def calcular_modulo_elasticidade(classe_concreto, tipo_agregado):
    """
    Realiza o cálculo dos módulos de elasticidade conforme NBR 6118:2023.
    
    Parâmetros:
    - classe_concreto (str): Ex: 'C20', 'C30', 'C50'.
    - tipo_agregado (str): 'Basalto', 'Granito', 'Calcário' ou 'Arenito'.
    
    Retorna:
    - dict: Dicionário com fck, alfa_E, alfa_i, Eci e Ecs para o HTML.
    """
    # 1. Extração do fck numérico (Ex: 'C30' -> 30)
    fck = int(classe_concreto.replace('C', ''))
    
    # 2. Definição do alfa_E (Coeficiente do Agregado)
    # Tabela 8.2.8 da Norma
    agregados = {
        "basalto": 1.2,
        "diabásio": 1.2,
        "granito": 1.0,
        "gnaisse": 1.0,
        "calcário": 0.9,
        "arenito": 0.7
    }
    
    # Busca o valor de alfa_E com base no texto de entrada
    alfa_e = 1.0  # Padrão para Granito/Gnaisse 
    tipo_busca = tipo_agregado.lower()
    for nome, valor in agregados.items():
        if nome in tipo_busca:
            alfa_e = valor
            break

    # 3. Cálculo do Eci (Módulo de Elasticidade Tangente Inicial) 
    # Fórmula para fck <= 50 MPa: Eci = alfa_E * 5600 * sqrt(fck)
    # Unidades: fck em MPa, resultado em MPa 
    eci = alfa_e * 5600 * math.sqrt(fck)
    
    # 4. Cálculo do alfa_i (Coeficiente para Módulo Secante) 
    # alfa_i = 0.8 + 0.2 * (fck / 80), limitado a 1.0 
    alfa_i = 0.8 + 0.2 * (fck / 80)
    if alfa_i > 1.0:
        alfa_i = 1.0
    
    # 5. Cálculo do Ecs (Módulo de Elasticidade Secante) 
    # Ecs = alfa_i * Eci
    ecs = alfa_i * eci

    return {
        "fck": fck,
        "agregado": tipo_agregado,
        "alfa_E": alfa_e,
        "alfa_i": alfa_i,
        "E_ci": eci,
        "E_cs": ecs
    }


def gerar_html_modulo_elasticidade(res, ativo=True):
    """
    Gera o código HTML formatado para o memorial de cálculo com numeração 'X)'.
    Se ativo=False, todas as cores destacadas tornam-se cinza.
    """
    if ativo:
        c_primaria = "#3498db" 
        c_sucesso = "#2ecc71"  
        c_alerta = "#f1c40f"   
        c_borda = "#444444"    
    else:
        c_primaria = "#888888"
        c_sucesso = "#888888"
        c_alerta = "#888888"
        c_borda = "#888888"

    html = f"""
    <html>
    <body style='font-family: "Times New Roman", serif; font-size: 13pt; color: white; line-height: 1.6; background-color: transparent;'>
        
        <div style='border-left: 5px solid {c_primaria}; padding-left: 15px; margin-bottom: 20px;'>
            <b style='font-size: 15pt; text-transform: uppercase;'>Memorial de Cálculo: Módulo de Elasticidade</b><br>
            <span style='font-size: 10pt; color: #bdc3c7;'>Referência: ABNT NBR 6118:2023 &sect; 8.2.8</span>
        </div>

        <div style='background: rgba(255,255,255,0.03); padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 20px; border: 1px dashed #555;'>
            <div style='font-style: italic; font-size: 13pt; margin-bottom: 8px;'>
                1) E<sub>ci</sub> = &alpha;<sub>E</sub> &sdot; 5600 &sdot; &radic;f<sub>ck</sub>
            </div>
            <div style='font-style: italic; font-size: 13pt; margin-bottom: 8px;'>
                2) &alpha;<sub>i</sub> = 0,8 + 0,2 &sdot; (f<sub>ck</sub> / 80) &le; 1,0
            </div>
            <div style='font-style: italic; font-size: 13pt;'>
                3) E<sub>cs</sub> = &alpha;<sub>i</sub> &sdot; E<sub>ci</sub>
            </div>
        </div>

        <div style='margin-bottom: 20px; padding-left: 10px;'>
            <b style='color: {c_primaria};'>Parâmetros Adotados:</b>
            <div style='font-family: "Courier New", monospace; font-size: 11pt; margin-top: 5px;'>
                &bull; Classe de Resistência: <b>C{res['fck']}</b> (f<sub>ck</sub> = {res['fck']} MPa)<br>
                &bull; Coeficiente do Agregado (&alpha;<sub>E</sub>): <b>{res['alfa_E']:.1f}</b> ({res['agregado']})
            </div>
        </div>

        <div style='margin-bottom: 20px;'>
            <b style='color: {c_primaria};'>Cálculo com Valores:</b>
            <div style='background: rgba(0,0,0,0.2); padding: 15px; border-radius: 8px; border: 1px solid {c_borda};'>
                <div style='font-style: italic; font-size: 12pt; margin-bottom: 10px;'>
                    1) E<sub>ci</sub> = {res['alfa_E']:.1f} &sdot; 5600 &sdot; &radic;{res['fck']} = 
                    <b style='color:{c_sucesso};'>{res['E_ci']:.2f} MPa</b>
                </div>
                <div style='font-style: italic; font-size: 12pt; margin-bottom: 10px;'>
                    2) &alpha;<sub>i</sub> = 0,8 + 0,2 &sdot; ({res['fck']} / 80) = 
                    <b style='color:{c_alerta};'>{res['alfa_i']:.3f}</b>
                </div>
                <div style='font-style: italic; font-size: 12pt;'>
                    3) E<sub>cs</sub> = {res['alfa_i']:.3f} &sdot; {res['E_ci']:.2f} = 
                    <b style='color:{c_sucesso};'>{res['E_cs']:.2f} MPa</b>
                </div>
            </div>
        </div>

        <div style='text-align: center; padding-top: 10px; border-top: 1px solid #555;'>
            <span style='font-size: 14pt;'>Módulo Secante Final (<b>E<sub>cs</sub></b>): </span>
            <span style='font-size: 18pt; color: {c_sucesso}; font-weight: bold;'>
                {res['E_cs']:.0f} MPa
            </span>
        </div>

    </body>
    </html>
    """
    return html


if __name__ == "__main__":
   
    # Teste 1: Seção Retangular Isolada + Gradiente (Aquecimento no topo)
    dados_ret = {"Tipo": "Retangular", "bw": 30, "h": 80}
    grad_ret = {"h1": 20, "h2": 15, "h3": 10, "deltat_1": 15, "deltat_2": 8, "deltat_3": 0}
    fig1 = desenhar_secao(dados_ret, gradiente=grad_ret)
    fig1.suptitle("Teste 1: Retangular Isolada", color='white', y=0.95)

    # Teste 2: Seção I com Laje Colaborante + Gradiente (Típico Eurocode/NBR 7188)
    # Note que h_total = h(I) + h_laje = 120 + 20 = 140 cm.
    dados_I = {"Tipo": "I", "bw": 20, "h": 120, "btf": 60, "hft": 10, "bfb": 50, "hfb": 15}
    grad_I = {"h1": 15, "h2": 25, "h3": 20, "deltat_1": 12, "deltat_2": 4, "deltat_3": 5}
    fig2 = desenhar_secao(dados_I, h_laje=20, largura_colaborante=180, gradiente=grad_I)
    fig2.suptitle("Teste 2: Seção I + Laje Colaborante", color='white', y=0.95)

    # Teste 3: Seção T isolada SEM gradiente (garantindo que não quebramos o funcionamento antigo)
    dados_T = {"Tipo": "T", "bw": 25, "h": 90, "bf": 80, "hf": 20}
    fig3 = desenhar_secao(dados_T)
    fig3.suptitle("Teste 3: Seção T (Sem Gradiente)", color='white', y=0.95)

    # Teste 4: FORÇANDO ERRO GEOMÉTRICO (Descomente para ver a trava agir)
    # grad_erro = {"h1": 50, "h2": 50, "h3": 50, "deltat_1": 10, "deltat_2": 5, "deltat_3": 2}
    # fig4 = desenhar_secao(dados_ret, gradiente=grad_erro) # Vai disparar ValueError

    plt.show()
   
    # Teste pesado: Viga I com Laje Colaborante (Simulando Viga de Ponte)
    # Aqui o CG fica jogado para cima por causa da laje, e as larguras mudam 4 vezes
    dados_ponte = {
        "Tipo": "I", 
        "bw": 20, 
        "h": 120, 
        "btf": 60, 
        "hft": 10, 
        "bfb": 50, 
        "hfb": 15
    }
    
    # Usando valores de Delta T da tabela 4 (Ex: Seção de 1.4m com revestimento de 100mm)
    gradiente_ponte = {
        "h1": 0.3 * 140, # h1 = 0,3h = 42 cm
        "h2": 25,        # max permitido por norma
        "h3": 20,        # max permitido por norma 
        "deltat_1": 13.5, 
        "deltat_2": 3.0, 
        "deltat_3": 2.5
    }

    resultados, memorial = calcular_gradiente_equivalente(
        dados=dados_ponte, 
        gradiente=gradiente_ponte, 
        h_laje=20, 
        largura_colaborante=180
    )

    resultado_modulo = calcular_modulo_elasticidade('C30','Granito/Gnaisse')
    print(gerar_html_modulo_elasticidade(resultado_modulo))