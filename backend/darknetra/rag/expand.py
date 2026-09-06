from darknetra.extract.validators import LEXICON


def query_expansions(query):
    expanded = []
    for canonical, (_, terms) in LEXICON.items():
        if canonical.casefold() in query.casefold() or any(
            term.casefold() in query.casefold() for term in terms
        ):
            expanded.extend(terms)
            expanded.append(canonical)
    return list(dict.fromkeys(expanded))
