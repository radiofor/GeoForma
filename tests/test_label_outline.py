from geoforma.rendering.label_item import outline_metrics


def test_outline_remains_legible_across_zoom_range():
    metrics = [outline_metrics(scale, 10000 * scale) for scale in (.001, .01, .1, 1, 10, 100)]
    assert all(1.2 <= width <= 2.2 and 2.5 <= dash <= 10 and 1.6 <= gap <= 6.5
               for width, dash, gap in metrics)
    assert all(a[0] <= b[0] and a[1] <= b[1] for a, b in zip(metrics, metrics[1:]))


def test_small_targets_have_shorter_dashes_and_selection_preserves_spacing():
    normal = outline_metrics(1, 20)
    large = outline_metrics(1, 1000)
    selected = outline_metrics(1, 20, True)
    assert normal[1] < large[1]
    assert selected[0] > normal[0] and selected[1:] == normal[1:]
