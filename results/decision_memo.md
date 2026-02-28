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

## 2. Optymalny deadband

| Broker | Deadband |
|--------|----------|
| XTB IKE | 0.068 (6.8%) |
| BOSSA IKE (promo) | 0.068 (6.8%) |
| mBank IKE (eMakler) | 0.068 (6.8%) |

Deadband chroni przed whipsawingiem i kompensuje koszty transakcyjne.
Przy XTB wyższy próg jest konieczny ze względu na 1% koszt FX na rotację.
mBank ma niższy koszt FX (0.2% round-trip), ale brak subkont walutowych
powoduje naliczenie FX na obu nogach każdej rotacji.

## 3. Uniwersum ETF

Rekomendowane: **U5**
U5 (5 ETF-ów): Sharpe=1.13, CAGR=17.26%

## 4. Walidacja Out-of-Sample

Średni OOS return per fold: 12.65%. Średni wybrany deadband: 0.030.

## 5. Scenariusze z regularnymi wpłatami

|   monthly_contribution |   bossa_ike_promo |   bossa_ike_standard |   mbank_ike |   taxed_account |   xtb_ike |
|-----------------------:|------------------:|---------------------:|------------:|----------------:|----------:|
|                      0 |           77875.9 |              73113.4 |     77182.3 |         56103.5 |   70813.4 |
|                    500 |          119571   |             111048   |    116495   |         85547.4 |  107560   |
|                   1000 |          161044   |             149383   |    156685   |        114991   |  144306   |
|                   2000 |          243081   |             226597   |    237939   |        173879   |  217800   |

## Podsumowanie decyzji

1. **Wybierz brokera** wg powyższej tabeli kosztowej i progu crossover.
2. **Ustaw deadband** na poziomie wskazanym powyżej dla wybranego brokera.
3. **Rozważ rozszerzenie koszyka** jeśli dane OOS to potwierdzają.
4. **Regularnie wpłacaj** — nawet małe kwoty znacząco podnoszą wartość końcową dzięki procentowi składanemu w parasolu IKE.
