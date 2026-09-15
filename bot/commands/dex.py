from bot.commands.stats import stats_response


def dex_page_response(records: list, index: int) -> str:
    record = records[index]
    return f"({index + 1}/{len(records)}) {stats_response(records, record['name'])}"
