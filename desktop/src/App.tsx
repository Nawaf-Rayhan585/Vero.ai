import { Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { APP_ROUTES } from "./app/routes";
import { AppShell } from "./components/layout/AppShell";
import { Spinner } from "./components/ui";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RegisterPage } from "./pages/RegisterPage";

function App() {
  const auth = useAuth();

  if (auth.status === "loading") {
    return <Spinner label="Loading" />;
  }

  if (auth.status === "signedOut") {
    return (
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  return (
    <AppShell>
      <Routes>
        {APP_ROUTES.map((route) => (
          <Route key={route.path} path={route.path} element={route.element} />
        ))}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppShell>
  );
}

export default App;
