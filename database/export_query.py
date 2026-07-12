async def get_all_transactions_for_export(user_id: int) -> list[dict]:
    """Все транзакции пользователя для экспорта в Excel."""
    async with get_db() as db:
        rows = await (
            await db.execute(
                """
                SELECT t.id, t.amount, t.is_income, t.note,
                       t.source, t.txn_date,
                       c.name AS category, c.icon AS cat_icon
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ?
                ORDER BY t.txn_date DESC, t.created_at DESC
                """,
                (user_id,),
            )
        ).fetchall()start
    return [dict(r) for r in rows]
