from datetime import datetime, timezone

def fetch():
    return [
        dict(
            title="NFP / Employment Situation — BLS",
            type="Macro",
            impact="high",
            start_ts=datetime(2026, 4, 3, 12, 30, tzinfo=timezone.utc),
            source_url="https://www.bls.gov/schedule/news_release/empsit.htm",
            summary="Employment Situation for March 2026",
        ),
        dict(
            title="Core PCE / Personal Income and Outlays — BEA",
            type="Macro",
            impact="high",
            start_ts=datetime(2026, 4, 9, 12, 30, tzinfo=timezone.utc),
            source_url="https://www.bea.gov/data/personal-consumption-expenditures-price-index",
            summary="Personal Income and Outlays release",
        ),
        dict(
            title="CPI (US Inflation) — BLS",
            type="Macro",
            impact="high",
            start_ts=datetime(2026, 4, 10, 12, 30, tzinfo=timezone.utc),
            source_url="https://www.bls.gov/schedule/news_release/cpi.htm",
            summary="Consumer Price Index for March 2026",
        ),
        dict(
            title="PPI (US Producer Inflation) — BLS",
            type="Macro",
            impact="high",
            start_ts=datetime(2026, 4, 14, 12, 30, tzinfo=timezone.utc),
            source_url="https://www.bls.gov/schedule/news_release/ppi.htm",
            summary="Producer Price Index for March 2026",
        ),
        dict(
            title="GDP (Advance Estimate) — BEA",
            type="Macro",
            impact="high",
            start_ts=datetime(2026, 4, 30, 12, 30, tzinfo=timezone.utc),
            source_url="https://www.bea.gov/news/schedule",
            summary="GDP (Advance Estimate), 1st Quarter 2026",
        ),
    ]
