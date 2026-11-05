"""Track accepted TF deliveries in the same callback that updates the buffer."""


class TransformReceiptTracking:
    """Mixin for tf2_ros.Buffer; no second TF subscription or new ROS executor."""

    def __init__(self, *args, on_transform, receipt_lock, **kwargs):
        self._on_transform = on_transform
        self._receipt_lock = receipt_lock
        super().__init__(*args, **kwargs)

    def set_transform(self, transform, authority):
        with self._receipt_lock:
            result = super().set_transform(transform, authority)
            self._on_transform(transform, False)
            return result

    def set_transform_static(self, transform, authority):
        with self._receipt_lock:
            result = super().set_transform_static(transform, authority)
            self._on_transform(transform, True)
            return result
