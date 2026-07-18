#!/usr/bin/env python3
"""
Abuse Hunter — офлайн-скрипт анализа CSV/JSON

Использование:
  python analyze.py --users users.csv --sessions sessions.csv --usage usage.csv --domain suspect.com

Требования к формату входных файлов (CSV, минимальный набор колонок):
  users.csv:     id, email, created_at
  sessions.csv:  user_id, session_id, user_agent, created_at
  usage.csv:     user_id, model_name, created_at, cost_usd (опционально)

Если доступен только users.csv, скрипт выполнит первые 3 шага (кластеризация доменов + ритм регистраций + паттерны префиксов).
"""

import argparse
import re
from collections import Counter
from datetime import datetime

import pandas as pd
import numpy as np


def load_csv(path):
    if not path:
        return None
    return pd.read_csv(path, parse_dates=[c for c in pd.read_csv(path, nrows=0).columns if 'at' in c.lower() or 'time' in c.lower()])


def extract_domain(email):
    if pd.isna(email) or '@' not in str(email):
        return None
    return str(email).split('@')[1].lower()


def extract_prefix(email):
    if pd.isna(email) or '@' not in str(email):
        return None
    return str(email).split('@')[0].lower()


def classify_prefix(prefix):
    if not prefix:
        return 'unknown'
    if re.match(r'^[a-z]+$', prefix):
        return 'letters_only'
    if re.match(r'^[0-9]+$', prefix):
        return 'digits_only'
    if re.match(r'^[a-z0-9]{6}$', prefix):
        return '6char_alnum'
    if re.match(r'^[a-z0-9]{5}$', prefix):
        return '5char_alnum'
    return 'other'


def score_dimension(name, value, thresholds):
    """Return 0/1/2 based on thresholds = [(max_for_0, max_for_1)]"""
    lo, hi = thresholds
    if value <= lo:
        return 0
    elif value <= hi:
        return 1
    return 2


def step1_domain_clustering(users_df):
    print("\n" + "="*60)
    print("ШАГ 1: Кластеризация email-доменов")
    print("="*60)

    users_df['domain'] = users_df['email'].apply(extract_domain)
    domain_stats = users_df.groupby('domain').agg(
        user_count=('id', 'count'),
        first_signup=('created_at', 'min'),
        last_signup=('created_at', 'max'),
    ).sort_values('user_count', ascending=False).head(20)

    domain_stats['span_hours'] = (domain_stats['last_signup'] - domain_stats['first_signup']).dt.total_seconds() / 3600

    print(domain_stats.to_string())
    return domain_stats


def step2_registration_tempo(users_df, domain):
    print("\n" + "="*60)
    print(f"ШАГ 2: Ритм регистраций — @{domain}")
    print("="*60)

    suspect = users_df[users_df['email'].str.contains(f'@{domain}', case=False, na=False)].sort_values('created_at')

    # Регистрации по дням
    daily = suspect.groupby(suspect['created_at'].dt.date).size()
    print("\nРегистрации по дням:")
    print(daily.to_string())

    # Интервалы между регистрациями
    intervals = suspect['created_at'].diff().dt.total_seconds().dropna()
    if len(intervals) > 0:
        median_interval = intervals.median()
        p90_interval = intervals.quantile(0.9)
        print(f"\nМедианный интервал регистраций: {median_interval:.1f} сек")
        print(f"P90 интервала регистраций: {p90_interval:.1f} сек")

        score = score_dimension('tempo', median_interval, (300, 60))
        # Инверсия: меньший интервал = больший риск
        score = 2 - score
        return score, median_interval
    return 0, None


def step3_prefix_pattern(users_df, domain):
    print("\n" + "="*60)
    print(f"ШАГ 3: Паттерны email-префиксов — @{domain}")
    print("="*60)

    suspect = users_df[users_df['email'].str.contains(f'@{domain}', case=False, na=False)]
    suspect = suspect.copy()
    suspect['prefix'] = suspect['email'].apply(extract_prefix)
    suspect['pattern'] = suspect['prefix'].apply(classify_prefix)

    pattern_dist = suspect['pattern'].value_counts()
    print("\nРаспределение паттернов префиксов:")
    print(pattern_dist.to_string())

    top_pattern_pct = pattern_dist.iloc[0] / len(suspect) * 100
    print(f"\nДоля самого частого паттерна: {top_pattern_pct:.1f}%")

    if top_pattern_pct > 80:
        return 2
    elif top_pattern_pct > 50:
        return 1
    return 0


def step4_ua_fingerprint(users_df, sessions_df, domain):
    if sessions_df is None:
        print("\n⚠️  ШАГ 4 пропущен: не предоставлены sessions-данные")
        return 0

    print("\n" + "="*60)
    print(f"ШАГ 4: UA-отпечатки и структура сессий — @{domain}")
    print("="*60)

    suspect_ids = set(users_df[users_df['email'].str.contains(f'@{domain}', case=False, na=False)]['id'])
    other_ids = set(users_df['id']) - suspect_ids

    s_suspect = sessions_df[sessions_df['user_id'].isin(suspect_ids)]
    s_other = sessions_df[sessions_df['user_id'].isin(other_ids)]

    sus_ua = s_suspect['user_agent'].nunique()
    sus_sessions = len(s_suspect)
    oth_ua = s_other['user_agent'].nunique()
    oth_sessions = len(s_other)

    sus_diversity = sus_ua / max(sus_sessions, 1)
    oth_diversity = oth_ua / max(oth_sessions, 1)

    print(f"Подозрительный домен: {sus_sessions} сессий, {sus_ua} UA, разнообразие {sus_diversity:.4f}")
    print(f"Все пользователи: {oth_sessions} сессий, {oth_ua} UA, разнообразие {oth_diversity:.4f}")
    print(f"Отношение разнообразия: {sus_diversity / max(oth_diversity, 0.0001):.2f}x")

    ratio = sus_diversity / max(oth_diversity, 0.0001)
    if ratio < 0.1:
        return 2
    elif ratio < 0.5:
        return 1
    return 0


def step5_activation(users_df, usage_df, domain):
    if usage_df is None:
        print("\n⚠️  ШАГ 5 пропущен: не предоставлены usage-данные")
        return 0

    print("\n" + "="*60)
    print(f"ШАГ 5: Время активации — @{domain}")
    print("="*60)

    first_usage = usage_df.groupby('user_id')['created_at'].min().rename('first_usage')
    merged = users_df.merge(first_usage, left_on='id', right_index=True, how='left')

    for label, mask in [('Подозрительный домен', merged['email'].str.contains(f'@{domain}', case=False, na=False)),
                         ('Все пользователи', ~merged['email'].str.contains(f'@{domain}', case=False, na=False))]:
        subset = merged[mask].dropna(subset=['first_usage'])
        if len(subset) > 0:
            activation = (subset['first_usage'] - subset['created_at']).dt.total_seconds()
            total = len(merged[mask])
            with_usage = len(subset)
            print(f"\n{label}:")
            print(f"  Покрытие использованием: {with_usage}/{total} = {with_usage/total*100:.1f}%")
            print(f"  Медиана активации: {activation.median():.0f} сек ({activation.median()/3600:.1f} ч)")

    return 1  # Упрощённая оценка


def step6_credits(users_df, usage_df, domain):
    if usage_df is None or 'cost_usd' not in usage_df.columns:
        print("\n⚠️  ШАГ 6 пропущен: не предоставлены данные о стоимости")
        return 0

    print("\n" + "="*60)
    print(f"ШАГ 6: Потребление кредитов / стоимость — @{domain}")
    print("="*60)

    suspect_ids = set(users_df[users_df['email'].str.contains(f'@{domain}', case=False, na=False)]['id'])
    sus_usage = usage_df[usage_df['user_id'].isin(suspect_ids)]

    total_cost = sus_usage['cost_usd'].sum()
    total_calls = len(sus_usage)
    unique_users = sus_usage['user_id'].nunique()

    print(f"Всего вызовов: {total_calls}")
    print(f"Аккаунтов с использованием: {unique_users}")
    print(f"Общая стоимость: ${total_cost:.2f}")

    if 'model_name' in sus_usage.columns:
        print("\nТоп-5 моделей по стоимости:")
        top_models = sus_usage.groupby('model_name').agg(
            calls=('user_id', 'count'),
            cost=('cost_usd', 'sum')
        ).sort_values('cost', ascending=False).head(5)
        print(top_models.to_string())

    if total_cost > 500:
        return 2
    elif total_cost > 100:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description='Abuse Hunter — расследование batch-регистраций в SaaS')
    parser.add_argument('--users', required=True, help='CSV с пользователями (id, email, created_at)')
    parser.add_argument('--sessions', help='CSV с сессиями (user_id, session_id, user_agent, created_at)')
    parser.add_argument('--usage', help='CSV с использованием (user_id, model_name, created_at, cost_usd)')
    parser.add_argument('--domain', required=True, help='Email-домен для расследования')
    args = parser.parse_args()

    users = load_csv(args.users)
    sessions = load_csv(args.sessions)
    usage = load_csv(args.usage)

    scores = {}

    step1_domain_clustering(users)

    score2, interval = step2_registration_tempo(users, args.domain)
    scores['Ритм регистраций'] = score2

    scores['Паттерны префиксов'] = step3_prefix_pattern(users, args.domain)
    scores['UA-отпечатки'] = step4_ua_fingerprint(users, sessions, args.domain)
    scores['Время активации'] = step5_activation(users, usage, args.domain)
    scores['Потребление кредитов'] = step6_credits(users, usage, args.domain)

    # Оценка кластеризации доменов
    suspect_count = len(users[users['email'].str.contains(f'@{args.domain}', case=False, na=False)])
    if suspect_count > 100:
        scores['Кластеризация доменов'] = 2
    elif suspect_count > 50:
        scores['Кластеризация доменов'] = 1
    else:
        scores['Кластеризация доменов'] = 0

    total = sum(scores.values())
    max_score = len(scores) * 2

    print("\n" + "="*60)
    print("Композитная оценка")
    print("="*60)
    for dim, s in scores.items():
        emoji = ['✅', '⚠️', '🚨'][s]
        print(f"  {emoji} {dim}: {s}/2")

    level = '✅ Норма' if total <= 3 else ('⚠️ Требуется наблюдение' if total <= 7 else '🚨 Высокий риск')
    print(f"\nИтого: {total}/{max_score} — {level}")


if __name__ == '__main__':
    main()
