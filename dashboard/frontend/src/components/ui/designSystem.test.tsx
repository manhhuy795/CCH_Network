import { fireEvent, render, screen } from "@testing-library/react";
import ConfirmDialog from "./ConfirmDialog";
import Drawer from "./Drawer";
import FeedbackState from "./FeedbackState";
import StatusBadge from "./StatusBadge";
import TaskProgress from "./TaskProgress";
import ToastRegion from "./ToastRegion";

describe("dashboard design system", () => {
  it("shows icon and text for status", () => {
    render(<StatusBadge status="degraded" />);
    expect(screen.getByRole("status")).toHaveTextContent("Suy giảm");
    expect(screen.getByRole("status").querySelector("svg")).toBeInTheDocument();
  });

  it("renders reusable loading and task states", () => {
    render(<><FeedbackState kind="loading" title="Đang tải" message="Vui lòng chờ" /><TaskProgress label="Đang Ping" elapsedSeconds={4} progress={40} /></>);
    expect(screen.getByText("Đang tải")).toBeInTheDocument();
    expect(screen.getByText("Đang Ping")).toBeInTheDocument();
    expect(screen.getByText("4s")).toBeInTheDocument();
  });

  it("confirms destructive actions", () => {
    const confirm = vi.fn();
    render(<ConfirmDialog open title="Ngắt liên kết?" message="Link sẽ chuyển DOWN." danger onConfirm={confirm} onClose={() => undefined} />);
    fireEvent.click(screen.getByText("Xác nhận"));
    expect(confirm).toHaveBeenCalledOnce();
  });

  it("supports drawer and dismissible toast", () => {
    const dismiss = vi.fn();
    render(<><Drawer open title="Node Inspector" onClose={() => undefined}>Chi tiết node</Drawer><ToastRegion items={[{ id: "1", message: "Đã lưu", tone: "success" }]} onDismiss={dismiss} /></>);
    expect(screen.getByLabelText("Node Inspector")).toHaveTextContent("Chi tiết node");
    fireEvent.click(screen.getByTitle("Đóng thông báo"));
    expect(dismiss).toHaveBeenCalledWith("1");
  });
});
