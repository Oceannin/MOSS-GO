import math
import unittest

from moss_go.reference_memory import reference_memory_shape


class ReferenceMemoryTests(unittest.TestCase):
    def test_shape_can_be_consumed_by_the_comfy_memory_estimator(self):
        shape = reference_memory_shape([(1, 128, 48, 64)], 128)
        # The native sampler appends each extra_conds_shapes value, then adds areas.
        condition_shapes = [shape, shape]
        input_shapes = [[2, 128, 48, 64], *condition_shapes]
        area = sum(item[0] * math.prod(item[2:]) for item in input_shapes)
        self.assertEqual(area, 4 * 48 * 64)

    def test_multiple_references_and_single_frame_latents_have_integer_dimensions(self):
        shape = reference_memory_shape([(1, 128, 48, 64), (1, 128, 1, 32, 32)], 128)
        self.assertEqual(shape, [1, 128, 48 * 64 + 32 * 32])
        self.assertTrue(all(isinstance(value, int) for value in shape))

    def test_invalid_shapes_are_rejected_instead_of_underestimating_memory(self):
        for shapes, channels in (([], 128), ([(1, 0, 4, 4)], 128), ([(1, 3, 3)], 4)):
            with self.subTest(shapes=shapes), self.assertRaises(ValueError):
                reference_memory_shape(shapes, channels)


if __name__ == "__main__":
    unittest.main()
