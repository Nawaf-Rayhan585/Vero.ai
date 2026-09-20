import { NavLink } from "react-router-dom";
import { APP_ROUTES } from "../../app/routes";
import "./Sidebar.css";

export function Sidebar() {
  return (
    <nav className="vero-sidebar" aria-label="Main navigation">
      <div className="vero-sidebar__brand">Vero.ai</div>
      <ul className="vero-sidebar__list">
        {APP_ROUTES.map((route) => (
          <li key={route.path}>
            <NavLink
              to={route.path}
              end={route.path === "/"}
              className={({ isActive }) =>
                "vero-sidebar__link" + (isActive ? " vero-sidebar__link--active" : "")
              }
            >
              {route.navLabel}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
