from pitchstems.acceleration import OnnxRuntimeStatus
import pitchstems.doctor as doctor


def test_doctor_checks_onnxruntime_import_for_basic_pitch(monkeypatch) -> None:
    monkeypatch.setattr(
        doctor,
        "onnxruntime_status",
        lambda: OnnxRuntimeStatus(installed=True, providers=["CUDAExecutionProvider"]),
    )

    checks = doctor.run_checks()

    assert any(
        check.name == "ONNX Runtime"
        and check.ok
        and "CUDAExecutionProvider" in check.detail
        for check in checks
    )


def test_doctor_reports_missing_onnxruntime(monkeypatch) -> None:
    monkeypatch.setattr(
        doctor,
        "onnxruntime_status",
        lambda: OnnxRuntimeStatus(installed=False, providers=[]),
    )

    checks = doctor.run_checks()

    assert any(
        check.name == "ONNX Runtime"
        and not check.ok
        and "onnxruntime-gpu" in check.detail
        for check in checks
    )
