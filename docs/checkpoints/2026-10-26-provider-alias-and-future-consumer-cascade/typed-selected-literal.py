# Publication excerpt. This header is newly added; the function below is exact.
# Only this pure function is runnable here; the operational selector is omitted.

# Exact source span: complete _selected_literal_equal function
def _selected_literal_equal(left, right):
    """Compare only selected literal snapshots, preserving every nested type."""
    if type(left)is not type(right):return False
    if type(left)is dict:
        return (len(left)==len(right) and all(any(
            _selected_literal_equal(key,other_key) and _selected_literal_equal(value,other_value)
            for other_key,other_value in right.items())for key,value in left.items()))
    if type(left)in(list,tuple):
        return len(left)==len(right) and all(_selected_literal_equal(a,b)for a,b in zip(left,right))
    if type(left)in(set,frozenset):
        return len(left)==len(right) and all(any(_selected_literal_equal(a,b)for b in right)for a in left)
    return left==right
