"""New publication-only stdlib controls; execute only the adjacent pure excerpt.

The literal fixtures are synthetic equality examples. They are never operational
requests, graph replacements, authorities or inputs to a product consumer.
"""
import copy
import json
from pathlib import Path
import runpy


def main():
    equal = runpy.run_path(str(Path(__file__).with_name('typed-selected-literal.py')))[
        '_selected_literal_equal']
    rows = []

    def check(name, left, right, expected):
        actual = equal(left, right)
        if actual is not expected:
            raise AssertionError(name)
        rows.append({'name': name, 'pass': True})

    unchanged = [None, False, True, 0, 1, 0.0, 1.0, '1', b'1',
                 [], (), {}, set(), frozenset(),
                 {'items': [{'number': 1, 'flags': (True, False),
                             'groups': {1, 2}, 'fixed': frozenset({3, 4})}]}]
    for index, value in enumerate(unchanged):
        check('unchanged_literal_' + str(index), value, copy.deepcopy(value), True)
    check('dictionary_order_is_irrelevant', {'a': 1, 'b': 2}, {'b': 2, 'a': 1}, True)
    check('set_order_is_irrelevant', {1, 2, 3}, {3, 1, 2}, True)
    check('tuple_with_unordered_nested_dictionary', ({'a': 1, 'b': 2},),
          ({'b': 2, 'a': 1},), True)

    changed = [
        ('scalar_bool_int', 1, True), ('scalar_int_float', 1, 1.0),
        ('scalar_bool_float', True, 1.0), ('zero_bool_int', 0, False),
        ('zero_int_float', 0, 0.0), ('string_int', '1', 1),
        ('bytes_string', b'1', '1'), ('none_bool', None, False),
        ('different_integer', 1, 2), ('different_string', 'a', 'b'),
        ('nested_list_bool', [{'v': (1,)}], [{'v': (True,)}]),
        ('nested_list_float', [{'v': (1,)}], [{'v': (1.0,)}]),
        ('dictionary_key_bool', {1: ['v']}, {True: ['v']}),
        ('dictionary_key_float', {1: ['v']}, {1.0: ['v']}),
        ('nested_tuple_key_bool', {('x', 1): [1]}, {('x', True): [1]}),
        ('nested_tuple_key_float', {('x', 1): [1]}, {('x', 1.0): [1]}),
        ('set_member_bool', {1, 2}, {True, 2}),
        ('set_member_float', {1, 2}, {1.0, 2}),
        ('frozenset_member_bool', frozenset({1, 2}), frozenset({True, 2})),
        ('frozenset_member_float', frozenset({1, 2}), frozenset({1.0, 2})),
        ('nested_set_member', {'v': [frozenset({(1,)})]},
                              {'v': [frozenset({(True,)})]}),
        ('list_tuple_container', [1], (1,)),
        ('set_frozenset_container', {1}, frozenset({1})),
        ('nested_container_type', {'v': [1]}, {'v': (1,)}),
        ('list_reorder', [1, 2], [2, 1]),
        ('list_length', [1], [1, 2]), ('tuple_length', (1,), (1, 2)),
        ('dictionary_added_key', {'a': 1}, {'a': 1, 'b': 2}),
        ('dictionary_removed_key', {'a': 1, 'b': 2}, {'a': 1}),
        ('dictionary_changed_key', {'a': 1}, {'b': 1}),
        ('set_length', {1}, {1, 2}),
    ]
    for name, left, right in changed:
        check(name, left, right, False)
        check(name + '_reverse', right, left, False)

    observations = []
    for label, replacement in [('bool', True), ('float', 1.0)]:
        selected = {'items': [{'number': 1}]}
        retained_reference = selected
        snapshot = copy.deepcopy(selected)
        selected['items'][0]['number'] = replacement
        if selected is not retained_reference or selected != snapshot:
            raise AssertionError('loose_equality_defect_not_reproduced')
        check('same_object_nested_' + label + '_mutation', selected, snapshot, False)
        observations.append({'case': label, 'same_container_identity': True,
                             'ordinary_equality_accepted_mutation': True,
                             'typed_comparator_rejected_mutation': True})
        selected['items'][0]['number'] = 1
        check('restored_exact_integer_after_' + label, selected, snapshot, True)
    if not (1 == True and 1 == 1.0 and True == 1.0):
        raise AssertionError('ordinary_numeric_equality_observation_changed')
    return {'pass': True, 'controls_count': len(rows), 'rows': rows,
            'first_loose_equality_defect_preserved': observations,
            'actual_future_proof_result_grant_clock_authority': None,
            'native_or_product_acceptance': False}


if __name__ == '__main__':
    print(json.dumps(main(), sort_keys=True, indent=2))
