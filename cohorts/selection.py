class InvalidSelection(ValueError):
    pass


def select_revisions(repository, members):
    if not isinstance(members, (list, tuple)):
        raise InvalidSelection('members must be ordered explicit revision pairs')
    seen, result = set(), []
    for pair in members:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or not isinstance(pair[0], str) or type(pair[1]) is not int
                or pair[1] < 1):
            raise InvalidSelection('invalid revision identity')
        if pair[0] in seen:
            raise InvalidSelection('select one revision per measurement')
        seen.add(pair[0])
        try:
            item = repository.get_revision(*pair)
        except KeyError as exc:
            raise InvalidSelection('unknown revision') from exc
        if item.withdrawn:
            raise InvalidSelection('withdrawn revision cannot be selected')
        result.append(item)
    return tuple(result)
