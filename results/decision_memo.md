# Rekomendacja końcowa — GEM na IKE

## Stan portfela
- Kapitał: 9,000 PLN
- Obecny koszyk: U5 (CNDX.L, EIMI.L, IWDA.L, IB01.L, CBU0.L)
- Obecnie wygrywający ETF: EIMI.L

## 1. Broker: BOSSA IKE (promo)

Przy kapitale 9000 PLN, najlepszy wynik końcowy daje BOSSA IKE (promo) (XTB IKE=46236 PLN, BOSSA IKE (promo)=62157 PLN, mBank IKE (eMakler)=58265 PLN).

### Porównanie modeli kosztowych

| Broker | FX/leg | Prowizja | Frakcje | Uwagi |
|--------|--------|----------|---------|-------|
| XTB IKE | 0.5% | 0% | Tak | Wysoki FX, brak cash drag |
| BOSSA IKE (promo) | 0% | 0% (promo) | Nie | Subkonta walutowe, promo do 2027 |
| mBank IKE (eMakler) | 0.1% | 0% (stale) | Nie | Brak subkont walutowych, FX na obu nogach rotacji |

### Warunki migracji
- BOSSA IKE (promo) > XTB od kapitału ~5,000 PLN
- mBank IKE (eMakler) > XTB od kapitału ~5,000 PLN

## Benchmark: IWDA.L (pasywny buy-and-hold)
- CAGR: 11.72%
- MaxDD: -24.05%
- Wartość końcowa: 42,822 PLN

## 2. Optymalny deadband — metodologia blend IS + OOS

**Wynik: deadband = 0.048 (4.8%)** (jednakowy dla wszystkich brokerów)

### Jak obliczono:
1. **Broker referencyjny**: BOSSA IKE (promo) (najtańszy IKE — najniższe tarcia kosztowe)
2. **IS optymalny** (in-sample): 0.068 (6.8%) — najwyższy excess CAGR
   spośród deadbandów, których MaxDD na brokerze referencyjnym nie przekracza MaxDD benchmarku
3. **OOS średnia** (walk-forward): 0.030 (3.0%)
4. **OOS mediana** (walk-forward): 0.040 (4.0%)
5. **Blend** = (IS optymalny + OOS średnia) / 2 = (0.068 + 0.030) / 2 = 0.0489
   → zaokrąglony do siatki: **0.048 (4.8%)**

Dlaczego blend: sam IS optymalny (6.8%) jest podatny na overfitting do danych
historycznych. OOS średnia (3.0%) pokazuje, co faktycznie wybiera walk-forward
na nowych danych. Uśrednienie daje kompromis odporny na overfitting.

### Wyniki per broker @ deadband = 0.048

| Broker | Excess CAGR | MaxDD | Sharpe |
|--------|-------------|-------|--------|
| XTB IKE | +2.96% | -24.21% | 0.97 |
| BOSSA IKE (promo) | +4.34% | -23.39% | 1.05 |
| mBank IKE (eMakler) | +4.09% | -23.03% | 1.04 |

## 3. Uniwersum ETF

Rekomendowane: **U5**
U5 (5 ETF-ów): Sharpe=1.19, CAGR=18.08%

## 4. Walidacja Out-of-Sample

Średni OOS return per fold: 14.58%.
Wybrane deadbandy per fold: ['0.000', '0.000', '0.050', '0.050', '0.052', '0.000', '0.000', '0.068', '0.068', '0.040', '0.000']

## 5. Scenariusze z regularnymi wpłatami

|   monthly_contribution |   bossa_ike_promo |   bossa_ike_standard |   mbank_ike |   taxed_account |   xtb_ike |
|-----------------------:|------------------:|---------------------:|------------:|----------------:|----------:|
|                      0 |           62254.3 |              56711   |     60509.9 |         43596.7 |   53051   |
|                    500 |           95142.3 |              85022.7 |     91893.4 |         66476.8 |   80580.2 |
|                   1000 |          128292   |             114727   |    123567   |         89356.9 |  108109   |
|                   2000 |          193496   |             174149   |    186720   |        135117   |  163168   |

## Podsumowanie decyzji

1. **Wybierz brokera** wg powyższej tabeli kosztowej i progu crossover.
2. **Ustaw deadband** na **4.8%** (blend IS + OOS, odporny na overfitting).
3. **Rozważ rozszerzenie koszyka** jeśli dane OOS to potwierdzają.
4. **Regularnie wpłacaj** — nawet małe kwoty znacząco podnoszą wartość końcową dzięki procentowi składanemu w parasolu IKE.
