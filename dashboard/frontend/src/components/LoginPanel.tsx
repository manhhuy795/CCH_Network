import { LogIn, ShieldCheck } from "lucide-react";

type Props = {
  username: string;
  password: string;
  busy: boolean;
  error?: string;
  onUsername: (value: string) => void;
  onPassword: (value: string) => void;
  onSubmit: () => void;
};

export default function LoginPanel(props: Props) {
  return (
    <section className="auth-page" aria-labelledby="login-title">
      <div className="auth-card">
        <div className="auth-card-icon"><ShieldCheck size={26} aria-hidden="true" /></div>
        <p className="eyebrow">CCH Network Operations</p>
        <h1 id="login-title">Đăng nhập hệ thống</h1>
        <p className="muted">Sử dụng tài khoản được cấp để truy cập dashboard theo đúng vai trò.</p>
        <form onSubmit={(event) => { event.preventDefault(); props.onSubmit(); }}>
          <label>
            Tên đăng nhập
            <input autoComplete="username" value={props.username} onChange={(event) => props.onUsername(event.target.value)} />
          </label>
          <label>
            Mật khẩu
            <input autoComplete="current-password" type="password" value={props.password} onChange={(event) => props.onPassword(event.target.value)} />
          </label>
          {props.error && <p className="form-error" role="alert">{props.error}</p>}
          <button className="primary auth-submit" type="submit" disabled={props.busy || !props.username.trim() || !props.password}>
            <LogIn size={17} aria-hidden="true" />
            {props.busy ? "Đang xác thực..." : "Đăng nhập"}
          </button>
        </form>
        <p className="auth-note">Phiên làm việc hết hạn sẽ yêu cầu đăng nhập lại. Không nhập operator token vào trình duyệt.</p>
      </div>
    </section>
  );
}
