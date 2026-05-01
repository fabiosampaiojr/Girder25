# =============================================================================
# Elementos_Finitos_Temperatura.py
# =============================================================================
# Motor de Elementos Finitos adaptado para análise de GRADIENTE TÉRMICO em
# estruturas de pórtico plano (vigas/pontes).
#
# ─── UNIDADES INTERNAS ───────────────────────────────────────────────────────
#   Comprimento : mm
#   Força       : N
#   Momento     : N·mm
#   E           : N/mm²  (MPa)
#   Inércia I   : mm⁴
#   Área A      : mm²
#   alpha       : 1/°C
#   h           : mm    (altura da seção transversal)
#   ΔT          : °C
#
# ─── CONVENÇÃO DE SINAIS ─────────────────────────────────────────────────────
#   Axial   : Tração positiva
#   Cortante: Positivo quando a face esquerda sobe em relação à direita
#   Momento : Positivo quando traciona as fibras inferiores (sagging)
#
# ─── ALTERAÇÕES REALIZADAS ───────────────────────────────────────────────────
#   • add_points_from_inputs  : removida duplicação/contradição de lógica
#   • generate_table_data     : generalizado para N apoios (era hardcoded em 4)
#   • calculate_internal_forces: removidos prints no loop (eram debug residual)
#   • plot_fem_diagrams       : removida referência a `data1` indefinida;
#                               substituída por implementação correta
#   • [NOVO] extract_reactions_fy : extrai Fy de qualquer número de apoios
#   • [NOVO] build_diagram_dicts  : monta dicionários de cortante/momento
#                                   no formato esperado pelo plotador
# =============================================================================

import numpy as np
import matplotlib.pyplot as plt
from typing import List, Sequence, Union, Optional

Number = Union[int, float]


# =============================================================================
# 1. FUNÇÕES DE RIGIDEZ E CÁLCULO TÉRMICO
# =============================================================================

def numeric_element_stiffness(I, E, A, L, theta_deg):
    """
    Retorna a matriz de rigidez global (Ke_global),
    a matriz de rigidez local (Ke_local) e a matriz de transformação (T).

    Parâmetros
    ----------
    I         : inércia à flexão [mm⁴]
    E         : módulo de elasticidade [N/mm²]
    A         : área da seção transversal [mm²]
    L         : comprimento do elemento [mm]
    theta_deg : inclinação do elemento [°] (0 = horizontal)
    """
    theta = np.radians(theta_deg)
    c, s = np.cos(theta), np.sin(theta)

    # Matriz de rigidez em coordenadas locais — [Fx1, Fy1, M1, Fx2, Fy2, M2]
    Ke_local = np.array([
        [ E*A/L,            0,           0, -E*A/L,            0,           0],
        [     0,  12*E*I/L**3,  6*E*I/L**2,      0, -12*E*I/L**3,  6*E*I/L**2],
        [     0,   6*E*I/L**2,    4*E*I/L,      0,  -6*E*I/L**2,    2*E*I/L],
        [-E*A/L,            0,           0,  E*A/L,            0,           0],
        [     0, -12*E*I/L**3, -6*E*I/L**2,      0,  12*E*I/L**3, -6*E*I/L**2],
        [     0,   6*E*I/L**2,    2*E*I/L,      0,  -6*E*I/L**2,    4*E*I/L],
    ])

    # Matriz de transformação (global → local)
    T_matrix = np.array([
        [ c,  s, 0,  0,  0, 0],
        [-s,  c, 0,  0,  0, 0],
        [ 0,  0, 1,  0,  0, 0],
        [ 0,  0, 0,  c,  s, 0],
        [ 0,  0, 0, -s,  c, 0],
        [ 0,  0, 0,  0,  0, 1],
    ])

    # K_global = T^T @ K_local @ T
    Ke_global = T_matrix.T @ Ke_local @ T_matrix

    return Ke_global, Ke_local, T_matrix


def calculate_element_thermal_forces(
    I: float, E: float, A: float, L: float, theta_deg: float,
    alpha: float, h: float, dT_avg: float, dT_grad: float
):
    """
    Calcula as forças nodais equivalentes de carregamento térmico para
    um elemento de pórtico.

    Parâmetros
    ----------
    I, E, A, L, theta_deg : propriedades geométrico-mecânicas do elemento
    alpha     : coeficiente de dilatação térmica [1/°C]
    h         : altura da seção transversal [mm]
    dT_avg    : variação de temperatura média (uniforme) [°C]
                → gera força axial de restrição
    dT_grad   : gradiente de temperatura = T_topo − T_base [°C]
                → gera momentos de restrição; positivo = topo mais quente

    Retorna
    -------
    f_eq_global : np.ndarray (6,)
        Forças nodais equivalentes em coordenadas GLOBAIS [N, N·mm].
    f_restritivo_local : np.ndarray (6,)
        Forças de restrição em coordenadas LOCAIS (usadas no pós-processamento).
    """
    # ── Forças de restrição (situação engastado-engastado) ────────────────
    # Axial: aquecimento uniforme → expansão bloqueada → compressão
    F_axial_rest = -E * A * alpha * dT_avg

    # Momento: gradiente bloqueia curvatura κ = alpha·ΔT_grad/h
    #   → Momento restritivo = E·I·κ
    #   Convenção local (anti-horário positivo):
    #     M1 = −M_mag  (horário no nó esquerdo para combater levantamento)
    #     M2 = +M_mag  (anti-horário no nó direito)
    M_rest_mag = (E * I * alpha * dT_grad / h) if h != 0 else 0.0

    # Vetor de restrição local: [Fx1, Fy1, M1, Fx2, Fy2, M2]
    f_restritivo_local = np.array([
        -F_axial_rest,   # Fx1
         0.0,            # Fy1 (sem cisalhamento térmico em viga reta homogênea)
        -M_rest_mag,     # M1
         F_axial_rest,   # Fx2
         0.0,            # Fy2
         M_rest_mag,     # M2
    ])

    # Forças nodais equivalentes = oposto das forças de restrição
    f_eq_local = -f_restritivo_local

    # Rotação para coordenadas globais
    theta = np.radians(theta_deg)
    c, s = np.cos(theta), np.sin(theta)
    T_matrix = np.array([
        [ c,  s, 0,  0,  0, 0],
        [-s,  c, 0,  0,  0, 0],
        [ 0,  0, 1,  0,  0, 0],
        [ 0,  0, 0,  c,  s, 0],
        [ 0,  0, 0, -s,  c, 0],
        [ 0,  0, 0,  0,  0, 1],
    ])
    f_eq_global = T_matrix.T @ f_eq_local

    return f_eq_global, f_restritivo_local


def find_thermal_props(x_mid: float, thermal_loads: list) -> Optional[tuple]:
    """
    Encontra as propriedades térmicas para o elemento de ponto médio x_mid.

    Parâmetros
    ----------
    x_mid         : posição central do elemento [mm]
    thermal_loads : [[x_ini, x_fim, alpha, h, dT_avg, dT_grad], ...]

    Retorna
    -------
    (alpha, h, dT_avg, dT_grad) ou None se x_mid não estiver em nenhuma zona.
    """
    if not thermal_loads:
        return None
    for load in thermal_loads:
        x_s, x_e, alpha, h, dt_avg, dt_grad = load
        if min(x_s, x_e) <= x_mid <= max(x_s, x_e):
            return (float(alpha), float(h), float(dt_avg), float(dt_grad))
    return None


# =============================================================================
# 2. MONTAGEM E SOLUÇÃO DO SISTEMA
# =============================================================================

def build_nodes_from_inputs(
    supports: Sequence[Sequence],
    section_params: Sequence[Sequence],
    *,
    round_to: Optional[int] = 0,
    as_numpy: bool = False,
    tol: float = 1e-6,
) -> Union[List[Number], np.ndarray]:
    """
    Retorna as coordenadas únicas e ordenadas dos nós a partir de:
      - supports      : [[x, 'tipo'], ...]
      - section_params: [[x_start, x_end, ...], ...]

    Os nós incluem os apoios e as extremidades de cada seção definida.
    """
    xs = []

    def _safe_x(entry):
        if entry is None or len(entry) == 0:
            return None
        try:
            return float(entry[0])
        except Exception:
            return None

    for s in supports or []:
        x = _safe_x(s)
        if x is not None:
            xs.append(x)

    for sec in section_params or []:
        if sec is None:
            continue
        if len(sec) >= 1:
            x0 = _safe_x([sec[0]])
            if x0 is not None:
                xs.append(x0)
        if len(sec) >= 2:
            x1 = _safe_x([sec[1]])
            if x1 is not None:
                xs.append(x1)

    if len(xs) == 0:
        return np.array([], dtype=float) if as_numpy else []

    xs = np.asarray(xs, dtype=float)

    if round_to is not None:
        xs_rounded = (np.round(xs).astype(int) if round_to == 0
                      else np.round(xs, round_to))
        uniq = np.unique(xs_rounded)
        out  = uniq.astype(int) if round_to == 0 else uniq
    else:
        xs_sorted = np.sort(xs)
        uniq = [xs_sorted[0]]
        for val in xs_sorted[1:]:
            if abs(val - uniq[-1]) > tol:
                uniq.append(val)
        out = np.array(uniq)

    if as_numpy:
        return np.asarray(out)
    if isinstance(out, np.ndarray) and np.issubdtype(out.dtype, np.integer):
        return out.tolist()
    if np.allclose(np.mod(out.astype(float), 1.0), 0.0, atol=1e-9):
        return [int(x) for x in out.tolist()]
    return out.tolist()


def add_points_from_inputs(
    supports: list,
    nodes_x: list,
) -> list:
    """
    Cria a lista de pontos nodais com condições de contorno de apoio.

    Cada ponto: [x, Fx, Fy, M, u, v, rot]
      Valores string → incógnita (a resolver)
      Valores 0      → prescrito (deslocamento ou força nula conhecida)

    Tipos de apoio
    --------------
    'fix' (engaste)  : u=0, v=0, rot=0
    'pin' (pino)     : u=0, v=0,  rot=livre → M=0 naturalmente pelo FEM
    'mov' (rolete)   : u=livre, v=0, rot=livre → M=0 naturalmente pelo FEM
    """
    # --- 1. Criar nós base com todas as grandezas como incógnitas ---
    points = []
    for i, x in enumerate(nodes_x, start=1):
        points.append([x, f'Fx{i}', f'Fy{i}', f'M{i}', f'u{i}', f'v{i}', f'rot{i}'])

    # --- 2. Nos nós sem apoio: forças externas são zero (sem carga aplicada) ---
    x_supports = {float(s[0]) for s in (supports or [])}
    for p in points:
        if p[0] not in x_supports:
            p[1] = 0  # Fx = 0
            p[2] = 0  # Fy = 0
            p[3] = 0  # M  = 0

    # --- 3. Auxiliar para localizar nó por coordenada x ---
    def idx_by_x(xval: float) -> int:
        for k, p in enumerate(points):
            if abs(p[0] - float(xval)) < 1e-6:
                return k
        return -1

    # --- 4. Aplicar condições de contorno dos apoios ---
    for x_sup, sup_type in (supports or []):
        idx = idx_by_x(float(x_sup))
        if idx == -1:
            raise ValueError(f"Apoio em x={x_sup} não encontrado na lista de nós.")

        typ = sup_type.strip().lower()

        if typ == 'fix':      # Engaste: bloqueia u, v e rotação
            points[idx][4] = 0  # u   = 0
            points[idx][5] = 0  # v   = 0
            points[idx][6] = 0  # rot = 0

        elif typ == 'pin':    # Pino: bloqueia u e v; rotação livre → M=0 pelo FEM
            points[idx][3] = 0  # M = 0 (força externa prescrita)
            points[idx][4] = 0  # u = 0
            points[idx][5] = 0  # v = 0
            # rot deixado como incógnita → livre

        elif typ == 'mov':    # Rolete: bloqueia apenas v; u e rot livres
            points[idx][1] = 0  # Fx = 0 (sem reação horizontal)
            points[idx][3] = 0  # M  = 0 (força externa prescrita)
            points[idx][5] = 0  # v  = 0
            # u e rot deixados como incógnitas → livres

        else:
            raise ValueError(f"Tipo de apoio desconhecido: '{sup_type}'. Use 'fix', 'pin' ou 'mov'.")

    return points


def boundary_conditions(points):
    """
    Extrai os vetores de forças (F) e deslocamentos (U) da lista de pontos.

    F = [Fx, Fy, M, Fx, Fy, M, ...]   (3 por nó)
    U = [u,  v,  rot, u,  v,  rot, ...]
    """
    F = np.array([val for p in points for val in p[1:4]], dtype=object)
    U = np.array([val for p in points for val in p[4:7]], dtype=object)
    return F, U


def elements_generator_with_sections(points, section_params):
    """
    Gera a lista de elementos e o total de graus de liberdade (GDL).

    Cada elemento: [I, E, A, L, theta, dof1, dof2, ..., dof6]
    onde dof_i são os índices globais (base 1).
    """
    n_nodes = len(points)
    if n_nodes < 2:
        raise ValueError("São necessários ao menos dois nós para formar um elemento.")

    elements = []
    for i in range(1, n_nodes):
        x_left  = float(points[i - 1][0])
        x_right = float(points[i][0])
        L_elem  = x_right - x_left
        if L_elem <= 0:
            raise ValueError(
                f"Elemento com comprimento inválido entre x={x_left} e x={x_right}."
            )

        x_mid   = 0.5 * (x_left + x_right)
        matched = None
        for xs, xe, I, E, A, theta in section_params:
            if min(xs, xe) <= x_mid <= max(xs, xe):
                matched = (float(I), float(E), float(A), float(theta))
                break
        if matched is None:
            raise ValueError(f"Nenhuma seção cobre o ponto médio x={x_mid}.")

        I_, E_, A_, theta_ = matched
        gdl_start = (i - 1) * 3 + 1
        dofs = list(range(gdl_start, gdl_start + 6))
        elements.append([I_, E_, A_, L_elem, theta_, *dofs])

    total_dof = n_nodes * 3
    return elements, total_dof


def assemble_global_stiffness(K_elements, total_dof):
    """
    Monta a matriz de rigidez global do sistema a partir das matrizes
    elementares empacotadas.
    """
    K_global = np.zeros((total_dof, total_dof), dtype=float)
    for Ke in K_elements:
        GDL = Ke[0, 1:].astype(int) - 1      # índices 0-based
        for i in range(6):
            for j in range(6):
                K_global[GDL[i], GDL[j]] += Ke[i + 1, j + 1]
    return K_global


def solve_fem_numeric(K_global, F_global, fixed_dofs):
    """
    Resolve K_global · U = F_global com condições de contorno de apoio.

    Retorna
    -------
    U_full : np.ndarray — vetor completo de deslocamentos
    R      : np.ndarray — vetor de reações (K·U − F); não nulo nos DOFs fixos
    """
    total_dof = K_global.shape[0]
    free_dofs = [i for i in range(total_dof) if i not in fixed_dofs]

    K_rr = K_global[np.ix_(free_dofs, free_dofs)]
    K_rf = K_global[np.ix_(free_dofs, fixed_dofs)]
    F_r  = F_global[free_dofs]
    U_f  = np.zeros(len(fixed_dofs))

    try:
        U_r = np.linalg.solve(K_rr, F_r - K_rf @ U_f)
    except np.linalg.LinAlgError:
        raise np.linalg.LinAlgError(
            "Matriz de rigidez singular. Verifique se a estrutura está "
            "adequadamente restringida (número e tipo de apoios)."
        )

    U_full = np.zeros(total_dof)
    U_full[free_dofs]  = U_r
    U_full[fixed_dofs] = U_f

    R = K_global @ U_full - F_global
    return U_full, R


# =============================================================================
# 3. FUNÇÃO PRINCIPAL — ORQUESTRADOR (FEM TÉRMICO)
# =============================================================================

def fem_thermal(
    supports: list,
    section_params: list,
    thermal_loads: list,
):
    """
    Executa a análise estrutural por Elementos Finitos para cargas TÉRMICAS.

    Parâmetros
    ----------
    supports : [[x_mm, tipo], ...]
        Posição e tipo dos apoios. Tipos: 'fix', 'pin', 'mov'.
    section_params : [[x_ini, x_fim, I, E, A, theta_deg], ...]
        Propriedades da seção em cada trecho.
    thermal_loads : [[x_ini, x_fim, alpha, h, dT_avg, dT_grad], ...]
        Zonas de carregamento térmico.

    Retorna
    -------
    U_full       : np.ndarray — deslocamentos e rotações nodais
    R            : np.ndarray — reações em todos os GDLs
    nodes_x      : list       — coordenadas X dos nós [mm]
    elements     : list       — lista de elementos
    element_data : list       — [(Ke_local, T, f_restritivo_local), ...]
    """
    # 1. Construir lista de nós
    nodes_x = build_nodes_from_inputs(supports, section_params)

    # 2. Criar estrutura de pontos (inclui condições de contorno)
    points = add_points_from_inputs(supports, nodes_x)

    # 3. Extrair vetores F e U
    F, U = boundary_conditions(points)

    # 4. Gerar elementos e GDLs
    elements, total_dof = elements_generator_with_sections(points, section_params)

    # 5. Calcular matrizes de rigidez e forças térmicas por elemento
    K_elements_packed  = []
    element_data       = []
    F_thermal_global   = np.zeros(total_dof)

    for i, el in enumerate(elements):
        I, E, A, L, theta, *dofs_1based = el

        x_left  = float(points[i][0])
        x_right = float(points[i + 1][0])
        x_mid   = 0.5 * (x_left + x_right)

        # Rigidez do elemento
        Ke_global_i, Ke_local_i, T_i = numeric_element_stiffness(I, E, A, L, theta)

        # Empacotamento para montagem global
        Ke_packed = np.zeros((7, 7))
        Ke_packed[0, 1:]  = dofs_1based
        Ke_packed[1:, 0]  = dofs_1based
        Ke_packed[1:, 1:] = Ke_global_i
        K_elements_packed.append(Ke_packed)

        # Forças térmicas equivalentes
        f_restritivo_local_i = np.zeros(6)
        thermal_props = find_thermal_props(x_mid, thermal_loads)

        if thermal_props:
            alpha, h, dt_avg, dt_grad = thermal_props
            f_eq_global_i, f_res_local_i = calculate_element_thermal_forces(
                I, E, A, L, theta, alpha, h, dt_avg, dt_grad
            )
            f_restritivo_local_i = f_res_local_i
            dofs_0based = [d - 1 for d in dofs_1based]
            for k in range(6):
                F_thermal_global[dofs_0based[k]] += f_eq_global_i[k]

        element_data.append((Ke_local_i, T_i, f_restritivo_local_i))

    # 6. Montar matriz de rigidez global
    K_global = assemble_global_stiffness(K_elements_packed, total_dof)

    # 7. Identificar DOFs fixos
    fixed_dofs = [i for i, val in enumerate(U) if val == 0]

    # 8. Converter forças externas para numérico (sempre zero neste módulo)
    def _to_float(f):
        return float(f) if isinstance(f, (int, float)) else 0.0

    F_externo = np.array([_to_float(f) for f in F], dtype=float)
    F_total   = F_externo + F_thermal_global

    # 9. Resolver o sistema
    U_full, R = solve_fem_numeric(K_global, F_total, fixed_dofs)

    return U_full, R, nodes_x, elements, element_data


# =============================================================================
# 4. PÓS-PROCESSAMENTO — ESFORÇOS INTERNOS
# =============================================================================

def calculate_internal_forces(
    U_full: np.ndarray,
    elements: list,
    element_data: list,
    nodes_x: list,
):
    """
    Calcula os esforços internos (axial, cortante, momento) em cada nó,
    incorporando os efeitos de cargas térmicas via f_restritivo_local.

    Convenção de sinais
    -------------------
    Axial    : tração positiva
    Cortante : positivo quando Fy no início do elemento aponta para cima
    Momento  : positivo quando traciona fibras inferiores (sagging)

    Retorna
    -------
    shear_results  : dict {x_mm: [V_N, ...]}
    moment_results : dict {x_mm: [M_Nmm, ...]}
    axial_results  : dict {x_mm: [N_N, ...]}

    Em nós intermediários (entre dois elementos), cada dicionário contém
    DOIS valores: o esforço ao fim do elemento esquerdo (índice 0) e
    o esforço ao início do elemento direito (índice 1). A diferença entre
    eles é a reação de apoio naquele nó.
    """
    shear_results  = {x: [] for x in nodes_x}
    moment_results = {x: [] for x in nodes_x}
    axial_results  = {x: [] for x in nodes_x}

    for i, (el, (Ke_local, T_matrix, f_restritivo_local)) in enumerate(
        zip(elements, element_data)
    ):
        dofs_1based = el[5:]
        dofs_0based = [d - 1 for d in dofs_1based]

        # Deslocamentos globais → locais
        u_global = U_full[dofs_0based]
        u_local  = T_matrix @ u_global

        # Forças locais finais: K_local · u_local + f_restritivo
        f_local = Ke_local @ u_local + f_restritivo_local

        # [Fx1, Fy1, M1, Fx2, Fy2, M2]
        Fx_i, Fy_i, M_i = f_local[0], f_local[1], f_local[2]
        Fx_j, Fy_j, M_j = f_local[3], f_local[4], f_local[5]

        x_i = nodes_x[i]
        x_j = nodes_x[i + 1]

        # Nó inicial (i) — esforços saindo do elemento para a esquerda
        axial_results[x_i].append(-Fx_i)    # Axial: compressão interna → tração no critério global
        shear_results[x_i].append(Fy_i)     # Cortante
        moment_results[x_i].append(-M_i)    # Momento (sinal conforme convenção)

        # Nó final (j) — esforços chegando no elemento pela direita
        axial_results[x_j].append(Fx_j)
        shear_results[x_j].append(-Fy_j)
        moment_results[x_j].append(M_j)

    return shear_results, moment_results, axial_results


# =============================================================================
# 5. FUNÇÕES UTILITÁRIAS PARA A CALCULADORA (NOVAS)
# =============================================================================

def extract_reactions_fy(
    R: np.ndarray,
    nodes_x: list,
    supports: list,
) -> dict:
    """
    Extrai as reações verticais (Fy) de qualquer número de apoios.

    Parâmetros
    ----------
    R        : vetor de reações completo retornado por fem_thermal
    nodes_x  : lista de coordenadas dos nós [mm]
    supports : [[x_mm, tipo], ...] — mesmo formato passado ao fem_thermal

    Retorna
    -------
    dict {x_mm_apoio: R_fy_N}
    """
    reactions = {}
    nodes_list = list(nodes_x)

    for x_sup, _ in supports:
        x_sup_f = float(x_sup)
        try:
            i_node = nodes_list.index(x_sup_f)
        except ValueError:
            # Busca por proximidade (tolerância de 0.5 mm)
            diffs = [abs(nx - x_sup_f) for nx in nodes_list]
            i_node = int(np.argmin(diffs))
            if diffs[i_node] > 0.5:
                continue

        fy_gdl = 3 * i_node + 1          # GDL de Fy no vetor global (0-based)
        reactions[x_sup_f] = float(R[fy_gdl])

    return reactions


def build_diagram_dicts(
    nodes_x: list,
    shear_results: dict,
    moment_results: dict,
    x_offset: float = 0.0,
) -> tuple:
    """
    Monta os dicionários de cortante e momento fletor no formato esperado
    pelo método `_plotar_diagrama` da calculadora.

    Formato das chaves
    ------------------
    Nós de extremidade (1 valor)  : "x_glob.3f"
    Nós intermediários (2 valores): "x_glob.3fe"  ← valor do elemento esquerdo
                                    "x_glob.3fd"  ← valor do elemento direito

    Os valores de cortante são expressos em kN e os de momento em kN·m.

    Parâmetros
    ----------
    nodes_x       : coordenadas dos nós em mm (sistema local do FEM)
    shear_results : {x_mm: [V_N, ...]}
    moment_results: {x_mm: [M_Nmm, ...]}
    x_offset      : deslocamento para converter para coordenadas globais [mm]

    Retorna
    -------
    (cortante_dict, momento_dict)
    """
    cortante_dict = {}
    momento_dict  = {}
    n = len(nodes_x)

    for i, x_loc in enumerate(nodes_x):
        x_glob = x_loc + x_offset
        key_base = f"{x_glob:.3f}"

        V_list = shear_results.get(x_loc, [0.0])
        M_list = moment_results.get(x_loc, [0.0])

        if len(V_list) == 2:
            # Nó intermediário → descontinuidade de cortante
            cortante_dict[key_base + 'e'] = V_list[0] / 1000.0   # N → kN
            cortante_dict[key_base + 'd'] = V_list[1] / 1000.0
        else:
            # Extremidade → ponto simples
            cortante_dict[key_base] = V_list[0] / 1000.0

        # Momento é contínuo: usa média dos dois valores se existir
        M_val = float(np.mean(M_list)) / 1e6                      # N·mm → kN·m
        momento_dict[key_base] = M_val

    return cortante_dict, momento_dict


def get_effort_at_x(
    x_coord_mm: float,
    nodes_x: list,
    V_results: dict,
    M_results: dict,
) -> tuple:
    """
    Calcula V e M em uma posição arbitrária por interpolação linear
    entre os nós adjacentes.

    Parâmetros
    ----------
    x_coord_mm : posição de interesse [mm]
    nodes_x    : coordenadas dos nós [mm]
    V_results  : {x_mm: [V_N, ...]}
    M_results  : {x_mm: [M_Nmm, ...]}

    Retorna
    -------
    (V_N, M_Nmm) no ponto x_coord_mm.
    """
    tol = 1e-6
    for i in range(len(nodes_x) - 1):
        x_i = nodes_x[i]
        x_j = nodes_x[i + 1]

        if not (x_i - tol <= x_coord_mm <= x_j + tol):
            continue

        # Índices das listas em cada nó (conforme o padrão de calculate_internal_forces)
        # Nó de início do elemento i:
        #   Se i == 0 → primeiro append (idx 0)
        #   Se i > 0  → segundo append (idx 1), pois o elem anterior já usou idx 0
        idx_i = 0 if i == 0 else 1
        idx_j = 0   # O nó final sempre recebe o primeiro append do elemento i

        try:
            V_i = V_results[x_i][idx_i]
            V_j = V_results[x_j][idx_j]
            M_i = M_results[x_i][idx_i]
            M_j = M_results[x_j][idx_j]
        except IndexError:
            return 0.0, 0.0

        L = x_j - x_i
        if L < tol:
            return V_i, M_i

        t = (x_coord_mm - x_i) / L
        V_at_x = V_i + t * (V_j - V_i)
        M_at_x = M_i + t * (M_j - M_i)
        return V_at_x, M_at_x

    return 0.0, 0.0


def generate_table_data(
    R_full: np.ndarray,
    nodes_x: list,
    V_results: dict,
    M_results: dict,
    supports: list,
    secoes_pre: dict,
) -> tuple:
    """
    Gera os dicionários de resultados formatados (versão genérica para N apoios).

    Parâmetros
    ----------
    R_full     : vetor de reações completo
    nodes_x    : coordenadas dos nós [mm]
    V_results  : {x_mm: [V_N, ...]}
    M_results  : {x_mm: [M_Nmm, ...]}
    supports   : [[x_mm, tipo], ...] — lista de apoios
    secoes_pre : {nome_seção: x_m}  — posições de seção em metros

    Retorna
    -------
    (reacoes_dict, cortante_dict, momento_dict)
    Reações em kN, cortante em kN, momento em kN·m.
    """
    # ── Reações verticais ────────────────────────────────────────────────────
    labels     = [chr(65 + k) for k in range(len(supports))]   # A, B, C, D, ...
    reacoes    = {}
    nodes_list = list(nodes_x)

    for (x_sup, _), label in zip(supports, labels):
        x_sup_f = float(x_sup)
        try:
            i_node = nodes_list.index(x_sup_f)
        except ValueError:
            diffs  = [abs(nx - x_sup_f) for nx in nodes_list]
            i_node = int(np.argmin(diffs))

        fy_gdl = 3 * i_node + 1
        reacoes[label] = round(float(R_full[fy_gdl]) / 1000.0, 3)   # N → kN

    # ── Cortante e Momento por seção ─────────────────────────────────────────
    cortante = {}
    momento  = {}
    for section_name, x_m in secoes_pre.items():
        x_mm = x_m * 1000.0
        V_N, M_Nmm = get_effort_at_x(x_mm, nodes_x, V_results, M_results)
        cortante[section_name] = round(V_N  / 1000.0,    3)   # N → kN
        momento[section_name]  = round(M_Nmm / 1_000_000, 3)  # N·mm → kN·m

    return reacoes, cortante, momento


# =============================================================================
# 6. PLOTAGEM (VERSÃO CORRIGIDA)
# =============================================================================

def plot_fem_diagrams(
    nodes_x: list,
    elements: list,
    element_data: list,
    U_full: np.ndarray,
    title_suffix: str = "",
) -> None:
    """
    Plota os diagramas de cortante e momento fletor percorrendo elemento
    por elemento, garantindo descontinuidade correta nos apoios.

    Parâmetros
    ----------
    nodes_x      : coordenadas dos nós [mm]
    elements     : lista de elementos
    element_data : [(Ke_local, T, f_restritivo_local), ...]  ← retorno de fem_thermal
    U_full       : vetor de deslocamentos
    title_suffix : sufixo para os títulos (ex.: "Caso 1 — Gradiente +50°C")
    """
    # Recalcula forças locais diretamente para garantir integridade
    xs_plot = []
    V_plot  = []
    M_plot  = []

    for i, (el, (Ke_local, T_matrix, f_restritivo_local)) in enumerate(
        zip(elements, element_data)
    ):
        dofs_0based = [d - 1 for d in el[5:]]
        u_global    = U_full[dofs_0based]
        u_local     = T_matrix @ u_global
        f_local     = Ke_local @ u_local + f_restritivo_local

        x_i = float(nodes_x[i])
        x_j = float(nodes_x[i + 1])

        V_i =  f_local[1]   # Fy início
        V_j = -f_local[4]   # Fy fim (sentido oposto)
        M_i = -f_local[2]   # M início (convenção sagging+)
        M_j =  f_local[5]   # M fim

        # Adiciona os dois pontos do elemento (linha pontilhada separa elementos)
        xs_plot.extend([x_i, x_j, np.nan])
        V_plot.extend([V_i, V_j, np.nan])
        M_plot.extend([M_i, M_j, np.nan])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    ax1.plot(xs_plot, V_plot, color='steelblue', linewidth=2)
    ax1.fill_between(
        [x for x in xs_plot if not (x is np.nan or (isinstance(x, float) and np.isnan(x)))],
        [v if not (v is np.nan or (isinstance(v, float) and np.isnan(v))) else 0
         for v in V_plot],
        0, color='steelblue', alpha=0.2
    )
    ax1.axhline(0, color='black', linewidth=1)
    ax1.set_title(f"Cortante (V){' — ' + title_suffix if title_suffix else ''}")
    ax1.set_ylabel("V [N]")
    ax1.grid(True, alpha=0.3)

    ax2.plot(xs_plot, M_plot, color='tomato', linewidth=2)
    ax2.axhline(0, color='black', linewidth=1)
    ax2.set_title(f"Momento Fletor (M){' — ' + title_suffix if title_suffix else ''}")
    ax2.set_ylabel("M [N·mm]")
    ax2.set_xlabel("Posição x [mm]")
    ax2.invert_yaxis()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


# =============================================================================
# BLOCO DE TESTE (executado apenas ao rodar o arquivo diretamente)
# =============================================================================
if __name__ == "__main__":

    # Viga contínua hiperestática de 3 vãos — gradiente térmico puro
    L_total = 57_500   # mm
    h_viga  =  1_800   # mm
    E       = 25_000   # N/mm²
    A       = 1.165e10 # mm²
    I       = 3.23e11  # mm⁴
    alpha   = 1e-5     # 1/°C

    supports = [
        [4_750,  'pin'],
        [18_750, 'mov'],
        [38_750, 'mov'],
        [52_750, 'mov'],
    ]
    section_params  = [[0.0, L_total, I, E, A, 0.0]]
    thermal_loads   = [[0.0, L_total, alpha, h_viga, 0.0, 10.0]]   # ΔT_grad = 10 °C

    U, R, nodes, elems, edata = fem_thermal(supports, section_params, thermal_loads)
    V_res, M_res, _           = calculate_internal_forces(U, elems, edata, nodes)

    print("Reações Fy [kN]:")
    reacs = extract_reactions_fy(R, nodes, supports)
    for x, r in sorted(reacs.items()):
        print(f"  x = {x/1000:.3f} m  →  Fy = {r/1000:.3f} kN")

    cortante_d, momento_d = build_diagram_dicts(nodes, V_res, M_res, x_offset=0.0)
    print(f"\n{len(cortante_d)} pontos no diagrama de cortante.")
    print(f"{len(momento_d)}  pontos no diagrama de momento.")
