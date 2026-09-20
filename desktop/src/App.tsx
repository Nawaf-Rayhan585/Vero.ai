import { Route, Routes } from "react-router-dom";
import { APP_ROUTES } from "./app/routes";
import { AppShell } from "./components/layout/AppShell";
import { NotFoundPage } from "./pages/NotFoundPage";

function App() {
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
