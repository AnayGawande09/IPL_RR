"""Plain-language reading of the 2022-24 -> 2025-26 holdout test (audit.json), shared by the report and the dashboard
so the wording always matches the numbers."""

def holdout_text(oo):
    def preds(role):
        return {k: v for k, v in oo[role].items() if isinstance(v, dict) and 'rho_vs_2025_26_pressure_RV' in v}
    out = []
    for role, lab in (('bat', 'batters'), ('bowl', 'bowlers')):
        P = preds(role)
        ours = P['Our composite (2022-24 only)']['rho_vs_2025_26_pressure_RV']
        best_k = max(P, key=lambda k: P[k]['rho_vs_2025_26_pressure_RV'])
        best = P[best_k]
        name = best_k.replace('Naive: ', '').replace('Our composite (2022-24 only)', 'our rating')
        if best_k.startswith('Our'):
            out.append(f"For {lab} our rating predicted best (ρ {ours:+.2f}).")
        elif best['ci90'][0] > 0 and max(abs(v['rho_vs_2025_26_pressure_RV']) for v in P.values() if v is not best) < best['rho_vs_2025_26_pressure_RV']:
            out.append(f"For {lab}, {name} predicted best (ρ {best['rho_vs_2025_26_pressure_RV']:+.2f}, interval above zero) against our rating's {ours:+.2f}.")
        else:
            out.append(f"For {lab} every predictor was close to zero (our rating {ours:+.2f}, best: {name} {best['rho_vs_2025_26_pressure_RV']:+.2f}), "
                       f"so pressure performance a season or two ahead is barely predictable at these sample sizes.")
    cb, cw = oo['bat']['components'], oo['bowl']['components']
    out.append(f"By component, the shrunk pressure run value (C2) carried forward best within our rating ({cb['C2 pressure RV']:+.2f} batters, "
               f"{cw['C2 pressure RV']:+.2f} bowlers), while the clutch delta did not ({cb['C3 clutch']:+.2f}, {cw['C3 clutch']:+.2f}).")
    return ' '.join(out)


def pm_verdict(pm):
    out = []
    for role, lab in (('bat', 'batters'), ('bowl', 'bowlers')):
        for k, h in pm['roles'][role]['head_to_head_2025_26'].items():
            a, b = h['public_model'], h['superrr_method']
            judge = "the model's own pressure rule" if 'model pressure rule' in k else 'our Leverage-Index pressure'
            win, w, l = ('the public model', a, b) if a['rho'] > b['rho'] else ('our method', b, a)
            sep = w['ci90'][0] > l['ci90'][1]
            out.append(f"For {lab} judged by {judge}, {win} was closer ({w['rho']:+.2f} vs {l['rho']:+.2f}; "
                       f"{'the 90% intervals do not overlap' if sep else 'the 90% intervals overlap, so this is not conclusive'}).")
    return '<b>Which is closer?</b> ' + ' '.join(out)


FEAT_WORDS = {'log_balls': 'career volume', 'val_all': 'overall run value', 'val_P': 'past pressure value', 'log_Pballs': 'pressure-ball volume',
              'last_val_P': 'last-season pressure value', 'last_val_all': 'last-season overall value', 'seasons': 'seasons played',
              'rate': 'strike rate or economy', 'bnd_or_dot': 'boundary or dot rate', 'out_or_wkt': 'dismissal or wicket rate',
              'played_last': 'played last season', 'death_share': 'share of balls at the death', 'log_price': 'auction price',
              'price_pct': "price rank in that auction", 'yrs_since_auction': 'years since auction', 'has_auction': 'has an auction record'}


def pm_uses(pm):
    out = []
    for role, lab in (('bat', 'batting'), ('bowl', 'bowling')):
        u = pm['roles'][role]['what_the_model_uses']
        top = sorted(u['values'].items(), key=lambda x: -abs(x[1]))[:4]
        if u['kind'].startswith('ridge'):
            txt = ', '.join(f"{FEAT_WORDS[f]} ({'+' if v > 0 else '−'})" for f, v in top)
            out.append(f"The {lab} model (ridge) leans most on {txt}, where + raises and − lowers the prediction.")
        else:
            txt = ', '.join(f"{FEAT_WORDS[f]} ({v:.0%} of splits)" for f, v in top)
            out.append(f"The {lab} model (boosted trees) spreads its splits widely, led by {txt}, a sign it found little stable signal.")
    return ' '.join(out)

