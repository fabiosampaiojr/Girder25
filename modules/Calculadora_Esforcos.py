# ============================================================================
# CALCULADORA_ESFORCOS.PY  –  Envoltória de Esforços por Combinação de Ações
# ============================================================================

from __future__ import annotations
import math
from itertools import groupby
from typing import Dict, List, Optional, Set, Tuple, Any
import numpy as np
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches

_COR_FUNDO_FIG = '#2b2b2b'
_COR_FUNDO_AX  = '#1e1e1e'
_COR_GRADE     = '#3a3a3a'
_COR_SPINE     = '#555555'
_COR_TICK      = '#b0b0b0'
_COR_ZERO      = '#607d8b'
_COR_LINHA_MAX = '#ffffff'
_COR_LINHA_MIN = '#90CAF9'
_COR_EXT_MAX   = '#A5D6A7'
_COR_EXT_MIN   = '#EF9A9A'
_COR_VIGA_REF  = '#4a4a4a'

COMB_PERMANENTE         = "Permanente"
COMB_PERM_CM            = "Permanente + Carga Móvel"
COMB_PERM_TEMP          = "Permanente + Temperatura"
COMB_PERM_CM_TEMP       = "Perm. + Carga Móvel + Temperatura"

COMB_CORES: Dict[str, str] = {
    COMB_PERMANENTE:   "#546e7a",
    COMB_PERM_CM:      "#1565C0",
    COMB_PERM_TEMP:    "#E65100",
    COMB_PERM_CM_TEMP: "#6A1B9A",
}

COMB_CORES_LINHA: Dict[str, str] = {
    COMB_PERMANENTE:   "#78909c",
    COMB_PERM_CM:      "#64b5f6",
    COMB_PERM_TEMP:    "#ffb74d",
    COMB_PERM_CM_TEMP: "#ce93d8",
}

# ============================================================================
# ─── FUNÇÕES DE PARSING DAS TABELAS DE ENTRADA ───────────────────────────────
# ============================================================================

def _parse_tabela_estatica(tabela: List[List], is_reacoes: bool = False) -> Dict[Tuple[float, str], float]:
    resultado: Dict[Tuple[float, str], float] = {}
    if not tabela or len(tabela) < 2: return resultado
    cabecalho = tabela[0]
    idx_pos = cabecalho.index("Posição [m]") if "Posição [m]" in cabecalho else 0
    idx_sec = cabecalho.index("Seção") if "Seção" in cabecalho else -1
    idx_apoio = cabecalho.index("Apoio") if "Apoio" in cabecalho else -1
    idx_val = len(cabecalho) - 1

    for linha in tabela[1:]:
        pos = round(float(linha[idx_pos]), 6)
        valor = float(linha[idx_val])
        sufixo = ""
        if is_reacoes:
            if idx_apoio != -1: sufixo = str(linha[idx_apoio]).strip()
        else:
            if idx_sec != -1:
                sec_str = str(linha[idx_sec]).lower()
                if "esq" in sec_str: sufixo = "e"
                elif "dir" in sec_str: sufixo = "d"
        resultado[(pos, sufixo)] = valor
    return resultado

def _parse_tabela_carga_movel(tabela: List[List], is_reacoes: bool = False) -> Dict[Tuple[float, str], Tuple[float, float]]:
    resultado: Dict[Tuple[float, str], Tuple[float, float]] = {}
    if not tabela or len(tabela) < 2: return resultado
    cabecalho = tabela[0]
    tem_phi = "φ" in cabecalho or len(cabecalho) >= (6 if not is_reacoes else 5)

    idx_pos = cabecalho.index("Posição [m]") if "Posição [m]" in cabecalho else (1 if is_reacoes else 0)
    idx_sec = cabecalho.index("Seção") if "Seção" in cabecalho else -1
    idx_apoio = cabecalho.index("Apoio") if "Apoio" in cabecalho else -1

    for linha in tabela[1:]:
        pos = round(float(linha[idx_pos]), 6)
        v_min, v_max = float(linha[-2]), float(linha[-1])
        sufixo = ""
        if is_reacoes:
            if idx_apoio != -1: sufixo = str(linha[idx_apoio]).strip()
        else:
            if idx_sec != -1:
                sec_str = str(linha[idx_sec]).lower()
                if "esq" in sec_str: sufixo = "e"
                elif "dir" in sec_str: sufixo = "d"
        resultado[(pos, sufixo)] = (v_min, v_max)
    return resultado

def _lookup_carga_movel(cm_dict: Dict[Tuple[float, str], Tuple[float, float]], pos: float, sufixo: str = '', tol: float = 0.01) -> Tuple[float, float]:
    chave_exata = (round(pos, 6), sufixo)
    if chave_exata in cm_dict: return cm_dict[chave_exata]
    for (p, s), vals in cm_dict.items():
        if s == sufixo and abs(p - pos) <= tol: return vals
    for (p, s), vals in cm_dict.items():
        if s == '' and abs(p - pos) <= tol: return vals
    return (0.0, 0.0)

def _lookup_estatica(est_dict: Dict[Tuple[float, str], float], pos: float, sufixo: str, tol: float = 0.01) -> float:
    chave_exata = (round(pos, 6), sufixo)
    if chave_exata in est_dict: return est_dict[chave_exata]
    for (p, s), v in est_dict.items():
        if s == sufixo and abs(p - pos) <= tol: return v
    for (p, s), v in est_dict.items():
        if s == '' and abs(p - pos) <= tol: return v
    return 0.0

# ============================================================================
# ─── FUNÇÕES DE COMBINAÇÃO ELU / ELS ─────────────────────────────────────────
# ============================================================================

def _combinar_ELU_max(Fgk: float, Fcm_max: float, Ftemp: float, coef: Dict[str, float]) -> Tuple[float, str]:
    gama_g, gama_q, gama_temp_q, psi0 = coef["gama_g"], coef["gama_q"], coef["gama_temp_q"], coef["psi0"]
    g = gama_g if Fgk >= 0.0 else 1.0
    cm_pos, temp_pos = Fcm_max > 0.0, Ftemp > 0.0
    if cm_pos and temp_pos: return g * Fgk + gama_q * Fcm_max + gama_temp_q * psi0 * Ftemp, COMB_PERM_CM_TEMP
    elif cm_pos: return g * Fgk + gama_q * Fcm_max, COMB_PERM_CM
    elif temp_pos: return g * Fgk + gama_temp_q * Ftemp, COMB_PERM_TEMP
    return g * Fgk, COMB_PERMANENTE

def _combinar_ELU_min(Fgk: float, Fcm_min: float, Ftemp: float, coef: Dict[str, float]) -> Tuple[float, str]:
    gama_g, gama_q, gama_temp_q, psi0 = coef["gama_g"], coef["gama_q"], coef["gama_temp_q"], coef["psi0"]
    g = 1.0 if Fgk >= 0.0 else gama_g
    cm_neg, temp_neg = Fcm_min < 0.0, Ftemp < 0.0
    if cm_neg and temp_neg: return g * Fgk + gama_q * Fcm_min + gama_temp_q * psi0 * Ftemp, COMB_PERM_CM_TEMP
    elif cm_neg: return g * Fgk + gama_q * Fcm_min, COMB_PERM_CM
    elif temp_neg: return g * Fgk + gama_temp_q * Ftemp, COMB_PERM_TEMP
    return g * Fgk, COMB_PERMANENTE

def _combinar_ELS_max(Fgk: float, Fcm_max: float, Ftemp: float, coef: Dict[str, float]) -> Tuple[float, str]:
    psi1, psi2 = coef["psi1"], coef["psi2"]
    cm_pos, temp_pos = Fcm_max > 0.0, Ftemp > 0.0
    if cm_pos and temp_pos: return Fgk + psi1 * Fcm_max + psi2 * Ftemp, COMB_PERM_CM_TEMP
    elif cm_pos: return Fgk + psi1 * Fcm_max, COMB_PERM_CM
    elif temp_pos: return Fgk + psi1 * Ftemp, COMB_PERM_TEMP
    return Fgk, COMB_PERMANENTE

def _combinar_ELS_min(Fgk: float, Fcm_min: float, Ftemp: float, coef: Dict[str, float]) -> Tuple[float, str]:
    psi1, psi2 = coef["psi1"], coef["psi2"]
    cm_neg, temp_neg = Fcm_min < 0.0, Ftemp < 0.0
    if cm_neg and temp_neg: return Fgk + psi1 * Fcm_min + psi2 * Ftemp, COMB_PERM_CM_TEMP
    elif cm_neg: return Fgk + psi1 * Fcm_min, COMB_PERM_CM
    elif temp_neg: return Fgk + psi1 * Ftemp, COMB_PERM_TEMP
    return Fgk, COMB_PERMANENTE

# ============================================================================
# ─── CLASSE PRINCIPAL ─────────────────────────────────────────────────────────
# ============================================================================

class CalculadoraEsforcos:
    def __init__(self, peso_proprio, sobrecarga, carga_movel, coeficientes_calculo: Dict[str, float], temperatura=None):
        self._pp   = peso_proprio
        self._sp   = sobrecarga
        self._cm   = carga_movel
        self._temp = temperatura
        self._coef = coeficientes_calculo
        self._tem_temperatura = temperatura is not None
        self._resultados: Optional[Dict] = None
        self._dados_plot: Dict = {}

    def calcular(self) -> Dict:
        self._resultados, self._dados_plot = {}, {}
        for estado in ("ELU", "ELS"):
            estado_res, dados_plot = self._calcular_estado(estado)
            self._resultados[estado] = estado_res
            self._dados_plot[estado] = dados_plot
        return self._resultados

    def plotar_envoltoria(self, estado: str, tipo: str) -> Figure:
        self._verificar_calculado()
        dp = self._dados_plot[estado][tipo]
        return self._plotar(estado=estado, tipo=tipo, posicoes=dp["posicoes"], maxs=dp["maxs"], mins=dp["mins"], combs_max=dp["combs_max"], combs_min=dp["combs_min"], labels=dp["labels"])

    def _calcular_estado(self, estado: str) -> Tuple[Dict, Dict]:
        pp_r, pp_v, pp_m = _parse_tabela_estatica(self._pp.reacoes, True), _parse_tabela_estatica(self._pp.cortante), _parse_tabela_estatica(self._pp.momento)
        sp_r, sp_v, sp_m = _parse_tabela_estatica(self._sp.reacoes, True), _parse_tabela_estatica(self._sp.cortante), _parse_tabela_estatica(self._sp.momento)
        tp_r = _parse_tabela_estatica(self._temp.reacoes, True) if self._tem_temperatura else {}
        tp_v = _parse_tabela_estatica(self._temp.cortante) if self._tem_temperatura else {}
        tp_m = _parse_tabela_estatica(self._temp.momento)  if self._tem_temperatura else {}

        cm_r, cm_v, cm_m = _parse_tabela_carga_movel(self._cm.reacoes, True), _parse_tabela_carga_movel(self._cm.cortante), _parse_tabela_carga_movel(self._cm.momento)

        tab_r, dp_r = self._montar_tabela(estado, pp_r, sp_r, cm_r, tp_r, "Reações",  "R")
        tab_v, dp_v = self._montar_tabela(estado, pp_v, sp_v, cm_v, tp_v, "Cortante", "V")
        tab_m, dp_m = self._montar_tabela(estado, pp_m, sp_m, cm_m, tp_m, "Momento",  "M")

        secoes_criticas = {"Reações": self._secoes_criticas(tab_r, "Reações"), "Cortante": self._secoes_criticas(tab_v, "Cortante"), "Momento": self._secoes_criticas(tab_m, "Momento")}
        return {"Reações": tab_r, "Cortante": tab_v, "Momento": tab_m, "Seções Críticas": secoes_criticas}, {"Reações": dp_r, "Cortante": dp_v, "Momento": dp_m}

    def _montar_tabela(self, estado, pp_dict, sp_dict, cm_dict, tp_dict, tipo_nome, simbolo) -> Tuple[List[List], Dict]:
        is_reacoes = (tipo_nome == "Reações")
        unidade = "[kNm]" if simbolo == "M" else "[kN]"
        header = ["Posição [m]", "Apoio" if is_reacoes else "Seção", f"{simbolo}sd_max {unidade}", f"{simbolo}sd_min {unidade}"]

        # Normalização com arredondamento rigoroso
        def normalizar_dict(d: Dict, is_cm: bool = False) -> Dict[Tuple[float, str], Any]:
            norm = {}
            for (pos, suf), val in d.items():
                pos_arred = round(pos, 6)
                chave = (pos_arred, suf)
                if chave not in norm:
                    norm[chave] = val
            return norm

        pp_norm = normalizar_dict(pp_dict)
        sp_norm = normalizar_dict(sp_dict)
        cm_norm = normalizar_dict(cm_dict, is_cm=True)
        tp_norm = normalizar_dict(tp_dict)

        tabela = [header]
        posicoes, maxs, mins, combs_max, combs_min, labels = [], [], [], [], [], []

        if is_reacoes:
            # Reações: comportamento original (sem descontinuidade)
            master_keys = set(pp_norm.keys()) | set(sp_norm.keys()) | set(cm_norm.keys()) | set(tp_norm.keys())
            chaves_ordenadas = sorted(master_keys, key=lambda k: (k[0], k[1]))
            for (pos, sufixo) in chaves_ordenadas:
                Fgk = _lookup_estatica(pp_norm, pos, sufixo) + _lookup_estatica(sp_norm, pos, sufixo)
                Ftemp = _lookup_estatica(tp_norm, pos, sufixo) if self._tem_temperatura else 0.0
                Fcm_min, Fcm_max = _lookup_carga_movel(cm_norm, pos, sufixo)

                if estado == "ELU":
                    val_max, comb_max = _combinar_ELU_max(Fgk, Fcm_max, Ftemp, self._coef)
                    val_min, comb_min = _combinar_ELU_min(Fgk, Fcm_min, Ftemp, self._coef)
                else:
                    val_max, comb_max = _combinar_ELS_max(Fgk, Fcm_max, Ftemp, self._coef)
                    val_min, comb_min = _combinar_ELS_min(Fgk, Fcm_min, Ftemp, self._coef)

                label_secao = sufixo
                tabela.append([round(pos, 4), label_secao, round(val_max, 4), round(val_min, 4)])
                posicoes.append(pos)
                maxs.append(val_max)
                mins.append(val_min)
                combs_max.append(comb_max)
                combs_min.append(comb_min)
                labels.append(label_secao)
        else:
            # ========== CORTANTE / MOMENTO - LÓGICA DEFINITIVA ==========
            todas_chaves = set(pp_norm.keys()) | set(sp_norm.keys()) | set(cm_norm.keys()) | set(tp_norm.keys())
            posicoes_unicas = sorted({pos for pos, suf in todas_chaves})

            for pos in posicoes_unicas:
                # Detecta se QUALQUER ação tem descontinuidade real
                tem_descontinuidade = any(
                    (pos, 'e') in d and (pos, 'd') in d
                    for d in (pp_norm, sp_norm, tp_norm, cm_norm)
                )

                sufixos = ['e', 'd'] if tem_descontinuidade else ['']

                for suf in sufixos:
                    Fgk = _lookup_estatica(pp_norm, pos, suf) + _lookup_estatica(sp_norm, pos, suf)
                    Ftemp = _lookup_estatica(tp_norm, pos, suf) if self._tem_temperatura else 0.0
                    Fcm_min, Fcm_max = _lookup_carga_movel(cm_norm, pos, suf)

                    if estado == "ELU":
                        val_max, comb_max = _combinar_ELU_max(Fgk, Fcm_max, Ftemp, self._coef)
                        val_min, comb_min = _combinar_ELU_min(Fgk, Fcm_min, Ftemp, self._coef)
                    else:
                        val_max, comb_max = _combinar_ELS_max(Fgk, Fcm_max, Ftemp, self._coef)
                        val_min, comb_min = _combinar_ELS_min(Fgk, Fcm_min, Ftemp, self._coef)

                    if suf == 'e':
                        label_secao = f"({pos:.2f} m) esq."
                    elif suf == 'd':
                        label_secao = f"({pos:.2f} m) dir."
                    else:
                        label_secao = f"({pos:.2f} m)"

                    tabela.append([round(pos, 4), label_secao, round(val_max, 4), round(val_min, 4)])
                    posicoes.append(pos)
                    maxs.append(val_max)
                    mins.append(val_min)
                    combs_max.append(comb_max)
                    combs_min.append(comb_min)
                    labels.append(label_secao)

        # Limpeza final de segurança (nunca mais 3+ linhas)
        tabela = self._limpar_tabela_final(tabela)

        return tabela, {
            "posicoes": posicoes, "maxs": maxs, "mins": mins,
            "combs_max": combs_max, "combs_min": combs_min, "labels": labels
        }

    @staticmethod
    def _limpar_tabela_final(tabela: List[List]) -> List[List]:
        """Garante no máximo 2 linhas por posição (esq/dir ou única)."""
        if len(tabela) < 2: return tabela
        agrupado = {}
        for linha in tabela[1:]:
            pos = round(float(linha[0]), 6)
            if pos not in agrupado:
                agrupado[pos] = []
            agrupado[pos].append(linha)

        dados_limpos = []
        for pos in sorted(agrupado.keys()):
            grupo = agrupado[pos]
            # Se tem esq e dir → mantém só esses
            esq = [l for l in grupo if "esq" in str(l[1]).lower()]
            dir_ = [l for l in grupo if "dir" in str(l[1]).lower()]
            if esq and dir_:
                dados_limpos.extend([esq[0], dir_[0]])
            else:
                # Mantém a única linha
                dados_limpos.append(grupo[0])

        return [tabela[0]] + dados_limpos

    def _secoes_criticas(self, tabela: List[List], tipo_nome: str) -> Dict[str, Tuple[str, float, float]]:
        if len(tabela) < 2: return {}
        dados, is_reacoes, idx_max, idx_min = tabela[1:], (tipo_nome == "Reações"), 2, 3
        def _label(l): return f"Apoio {l[1]} ({float(l[0]):.2f} m)" if is_reacoes else f"{l[1]}"
        lnh_max = dados[max(range(len(dados)), key=lambda i: float(dados[i][idx_max]))]
        lnh_min = dados[min(range(len(dados)), key=lambda i: float(dados[i][idx_min]))]
        return {
            "Máximo": (_label(lnh_max), round(float(lnh_max[idx_min]), 4), round(float(lnh_max[idx_max]), 4)),
            "Mínimo": (_label(lnh_min), round(float(lnh_min[idx_min]), 4), round(float(lnh_min[idx_max]), 4)),
        }

    # ... (o restante do arquivo permanece exatamente igual: _plotar, _verificar_calculado, etc.)

    def _plotar(self, estado, tipo, posicoes, maxs, mins, combs_max, combs_min, labels) -> Figure:
        # (código idêntico ao anterior - não alterado)
        unidade_label, simbolo, inverter_y = ("kN·m" if tipo == "Momento" else "kN"), {"Cortante": "V", "Momento": "M", "Reações": "R"}[tipo], (tipo == "Momento")
        xs, mxs, mns = np.array(posicoes, dtype=float), np.array(maxs, dtype=float), np.array(mins, dtype=float)

        fig = Figure(figsize=(9.61, 5.71), dpi=100)
        ax  = fig.add_subplot(111)
        fig.patch.set_facecolor(_COR_FUNDO_FIG); ax.set_facecolor(_COR_FUNDO_AX)
        for spine in ax.spines.values(): spine.set_color(_COR_SPINE); spine.set_linewidth(0.8)
        ax.tick_params(colors=_COR_TICK, labelsize=8.5, length=4, width=0.7); ax.xaxis.label.set_color(_COR_TICK); ax.yaxis.label.set_color(_COR_TICK)

        if len(xs) == 0:
            ax.text(0.5, 0.5, "Sem dados disponíveis.", color='white', ha='center', va='center', transform=ax.transAxes, fontsize=11)
            fig.subplots_adjust(left=0.09, right=0.97, top=0.87, bottom=0.10)
            return fig

        ax.yaxis.grid(True, color=_COR_GRADE, linewidth=0.5, linestyle='--', alpha=0.7, zorder=1)
        for xp in xs: ax.axvline(xp, color=_COR_GRADE, linewidth=0.35, linestyle=':', alpha=0.45, zorder=1)
        ax.axhline(0.0, color=_COR_ZERO, linewidth=1.2, linestyle='-', alpha=0.9, zorder=4)

        _preencher_combinacoes(ax, xs, mxs, np.zeros_like(mxs), combs_max, alpha=0.50, zorder=2)
        _preencher_combinacoes(ax, xs, np.zeros_like(mns), mns, combs_min, alpha=0.40, zorder=2)
        _desenhar_linha_combinacao(ax, xs, mxs, combs_max, lw=1.2, zorder=5)
        _desenhar_linha_combinacao(ax, xs, mns, combs_min, lw=1.2, zorder=5, dashed=True)

        ax.plot(xs, mxs, color=_COR_LINHA_MAX, linewidth=2.2, zorder=6, label=f'{simbolo}$_{{sd,max}}$')
        ax.plot(xs, mns, color=_COR_LINHA_MIN, linewidth=2.0, zorder=6, linestyle='--', label=f'{simbolo}$_{{sd,min}}$')
        _marcar_secoes(ax, xs, labels)

        if len(mxs) > 0:
            idx_mx, idx_mn = int(np.argmax(mxs)), int(np.argmin(mns))
            def _fmt_label(lbl, x_val): return lbl if 'm' in lbl.lower() or ',' in lbl else f"({x_val:.2f} m)".replace('.', ',')
            _anotar_extremo(ax, xs, mxs, mns, idx_mx, f"Máx: {mxs[idx_mx]:+.2f} {unidade_label}\n{_fmt_label(labels[idx_mx], xs[idx_mx])}", _COR_EXT_MAX, True, inverter_y)
            _anotar_extremo(ax, xs, mxs, mns, idx_mn, f"Mín: {mns[idx_mn]:+.2f} {unidade_label}\n{_fmt_label(labels[idx_mn], xs[idx_mn])}", _COR_EXT_MIN, False, inverter_y)

        margem_x = 0.03 * (xs[-1] - xs[0]) if len(xs) > 1 else 0.5
        ax.set_xlim(xs[0] - margem_x, xs[-1] + margem_x)
        span = max(mxs.max(), 0.0) - min(mns.min(), 0.0)
        ax.set_ylim(min(mns.min(), 0.0) - 0.22 * span, max(mxs.max(), 0.0) + 0.22 * span)
        ax.set_xlabel("Posição [m]", fontsize=10, labelpad=6); ax.set_ylabel(f"{simbolo}$_{{sd}}$ [{unidade_label}]", fontsize=10, labelpad=6)

        if inverter_y:
            ax.invert_yaxis()
            ax.text(0.01, 0.02, "↓ M⁺ → tração inferior", transform=ax.transAxes, color=_COR_TICK, fontsize=7, alpha=0.65)

        _montar_legenda(ax, combs_max, combs_min, simbolo)
        _montar_titulos(fig, ax, estado, tipo, self._coef, self._tem_temperatura)

        fig._envoltoria_data = {'ax': ax, 'xs': xs, 'mxs': mxs, 'mns': mns, 'labels': labels, 'combs_max': combs_max, 'combs_min': combs_min, 'unidade': unidade_label, 'simbolo': simbolo, 'inverter_y': inverter_y}
        fig.subplots_adjust(left=0.09, right=0.97, top=0.87, bottom=0.10)
        return fig

    def _verificar_calculado(self):
        if self._resultados is None: raise RuntimeError("Análise não executada.")

# Funções auxiliares de plotagem (permanece igual)
def _preencher_combinacoes(ax, xs, ys_superior, ys_inferior, combinacoes, alpha=0.50, zorder=2):
    indices = range(len(xs) - 1)
    for comb, grupo in groupby(indices, key=lambda i: combinacoes[i]):
        idxs = list(grupo)
        seg  = slice(idxs[0], idxs[-1] + 2)
        ax.fill_between(xs[seg], ys_superior[seg], ys_inferior[seg], facecolor=COMB_CORES.get(comb, '#607d8b'), alpha=alpha, linewidth=0, zorder=zorder)

def _desenhar_linha_combinacao(ax, xs, ys, combinacoes, lw=1.2, zorder=5, dashed=False):
    ls = '--' if dashed else '-'
    indices = range(len(xs) - 1)
    for comb, grupo in groupby(indices, key=lambda i: combinacoes[i]):
        idxs = list(grupo)
        seg  = slice(idxs[0], idxs[-1] + 2)
        ax.plot(xs[seg], ys[seg], color=COMB_CORES_LINHA.get(comb, '#78909c'), linewidth=lw, linestyle=ls, alpha=0.70, solid_capstyle='butt', zorder=zorder)

def _marcar_secoes(ax, xs, labels):
    if len(xs) == 0: return
    span = xs[-1] - xs[0] if xs[-1] != xs[0] else 1.0
    min_dist = span * 0.08
    ticks_x, ultimo_x = [], -math.inf
    for i, x in enumerate(xs):
        if i == 0 or i == len(xs) - 1 or (x - ultimo_x) >= min_dist:
            ticks_x.append(x)
            ultimo_x = x
    ax.set_xticks(ticks_x)
    ax.set_xticklabels([f"{x:.2f}" for x in ticks_x], fontsize=8.0, color=_COR_TICK)

def _anotar_extremo(ax, xs, mxs, mns, idx, texto, cor, acima, inverter):
    x_val, y_val = xs[idx], mxs[idx] if acima else mns[idx]
    ax.scatter([x_val], [y_val], s=60, color=cor, zorder=9, edgecolors='none', alpha=0.95)
    span = max(mxs.max(), 0.0) - min(mns.min(), 0.0)
    offset_dados = 0.12 * span
    sobe_no_plot = acima != inverter
    y_text = y_val + (offset_dados if sobe_no_plot else -offset_dados)
    ax.annotate(texto, xy=(x_val, y_val), xytext=(x_val, y_text), fontsize=8.0, fontweight='bold', color=cor, ha='center', va='bottom' if sobe_no_plot else 'top', arrowprops=dict(arrowstyle='-|>', color=cor, lw=0.9, mutation_scale=10), bbox=dict(boxstyle='round,pad=0.35', facecolor=_COR_FUNDO_FIG, edgecolor=cor, linewidth=0.8, alpha=0.92), zorder=10)

def _montar_legenda(ax, combs_max, combs_min, simbolo):
    presentes = sorted(set(combs_max) | set(combs_min), key=lambda c: list(COMB_CORES.keys()).index(c) if c in COMB_CORES else 99)
    handles = [mpatches.Patch(facecolor=COMB_CORES.get(c, '#607d8b'), edgecolor=COMB_CORES_LINHA.get(c, '#607d8b'), linewidth=0.8, alpha=0.75, label=c) for c in presentes]
    handles += [mpatches.Patch(facecolor='none', edgecolor='none', label=' '), Line2D([0], [0], color=_COR_LINHA_MAX, linewidth=2.0, linestyle='-', label=f'{simbolo}$_{{sd,max}}$'), Line2D([0], [0], color=_COR_LINHA_MIN, linewidth=2.0, linestyle='--', label=f'{simbolo}$_{{sd,min}}$')]
    leg = ax.legend(handles=handles, fontsize=8.0, loc='upper right', framealpha=0.92, edgecolor=_COR_SPINE)
    leg.get_frame().set_facecolor(_COR_FUNDO_FIG)
    for txt in leg.get_texts(): txt.set_color(_COR_TICK)

def _montar_titulos(fig, ax, estado, tipo, coef, tem_temp):
    comb_nome = "Normal" if estado == "ELU" else "Frequente"
    fig.text(0.50, 0.960, f"Envoltória de {tipo}  ·  {estado}  (Combinação {comb_nome})", ha='center', va='top', fontsize=10.5, fontweight='bold', color='white')
    partes = [f"γ$_g$={coef['gama_g']:.1f}", f"γ$_q$={coef['gama_q']:.1f}", f"ψ₀={coef['psi0']:.1f}"] if estado == "ELU" else [f"ψ₁={coef['psi1']:.1f}", f"ψ₂={coef['psi2']:.1f}"]
    if estado == "ELU" and tem_temp: partes.append(f"γ$_{{temp}}$={coef['gama_temp_q']:.1f}")
    fig.text(0.50, 0.910, " | ".join(partes), ha='center', va='top', fontsize=8.0, color=_COR_TICK, alpha=0.85)

def ativar_interatividade(fig: Figure, canvas) -> None:
    # (código idêntico ao anterior - não alterado)
    from PyQt6.QtCore import QTimer
    data = getattr(fig, '_envoltoria_data', None)
    if not data: return
    ax, xs, mxs, mns, labels = data['ax'], data['xs'], data['mxs'], data['mns'], data['labels']
    unidade, simbolo, inverter_y = data['unidade'], data['simbolo'], data['inverter_y']
    y_lo_orig, y_hi_orig = ax.get_ylim()

    vline,   = ax.plot([], [], color='#FFA726', lw=0.9, linestyle='--', alpha=0.0, zorder=8)
    dot_max  = ax.scatter([], [], s=50, color=_COR_EXT_MAX, zorder=9, alpha=0.0, edgecolors='none')
    dot_min  = ax.scatter([], [], s=50, color=_COR_EXT_MIN, zorder=9, alpha=0.0, edgecolors='none')
    tooltip  = ax.text(0.018, 0.975, '', transform=ax.transAxes, fontsize=8.0, color='white', va='top', bbox=dict(boxstyle='round,pad=0.50', facecolor='#0d0d1a', edgecolor='#90CAF9', alpha=0.0), zorder=20, visible=False)

    _pending, _timer = {'event': None}, QTimer()
    _timer.setSingleShot(True); _timer.setInterval(30)

    def _flush():
        event = _pending['event']
        if event is None: return
        if event.inaxes is not ax or event.xdata is None:
            vline.set_alpha(0); dot_max.set_alpha(0); dot_min.set_alpha(0); tooltip.set_visible(False)
        else:
            idx = int(np.argmin(np.abs(xs - event.xdata)))
            x_sec, mx, mn = float(xs[idx]), float(mxs[idx]), float(mns[idx])
            vline.set_data([x_sec, x_sec], ax.get_ylim()); vline.set_alpha(0.55)
            dot_max.set_offsets([[x_sec, mx]]); dot_max.set_alpha(0.9)
            dot_min.set_offsets([[x_sec, mn]]); dot_min.set_alpha(0.9)
            tooltip.set_text(f"  {labels[idx]}\n  {simbolo}sd,max = {mx:+.3f} {unidade}\n  {simbolo}sd,min = {mn:+.3f} {unidade}")
            tooltip.get_bbox_patch().set_alpha(0.93); tooltip.set_visible(True)
        canvas.draw_idle()

    _timer.timeout.connect(_flush)
    def on_move(event):
        _pending['event'] = event
        if not _timer.isActive(): _timer.start()

    def on_scroll(event):
        if event.inaxes is not ax: return
        y_lo, y_hi = ax.get_ylim()
        y_c = event.ydata if event.ydata else (y_lo + y_hi) / 2
        fator = 0.85 if event.button == 'up' else (1 / 0.85)
        ax.set_ylim(y_c - (y_c - y_lo) * fator, y_c + (y_hi - y_c) * fator); canvas.draw_idle()

    def on_click(event):
        if event.inaxes is ax and event.dblclick: ax.set_ylim(y_lo_orig, y_hi_orig); canvas.draw_idle()

    canvas.mpl_connect('motion_notify_event', on_move)
    canvas.mpl_connect('scroll_event', on_scroll)
    canvas.mpl_connect('button_press_event', on_click)