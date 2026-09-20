import type { ButtonHTMLAttributes } from "react";
import "./Button.css";

type Variant = "primary" | "secondary";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = "secondary", className, ...rest }: ButtonProps) {
  const classes = ["vero-button", `vero-button--${variant}`, className].filter(Boolean).join(" ");
  return <button className={classes} {...rest} />;
}
