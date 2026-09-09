"use client";
import { useRef } from "react";
import { Clock3, Repeat2, Globe2 } from "lucide-react";

export const weekDays = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];
export type ScheduleChoice = {
  repeat: "daily" | "weekdays" | "weekly" | "interval" | "custom";
  time: string;
  days: number[];
  interval: string;
  intervalUnit?: "minutes" | "hours";
  weeklyDay?: number;
};
const intervals = {
  minutes: [1, 2, 3, 5, 10, 15, 20, 30],
  hours: [1, 2, 3, 4, 6, 8, 12],
};
export function scheduleExpression(choice: ScheduleChoice) {
  if (choice.repeat === "interval") {
    const unit = choice.intervalUnit || "minutes";
    if (!intervals[unit]?.includes(Number(choice.interval))) return "";
    const interval = Number(choice.interval);
    if (unit === "hours")
      return interval === 1 ? "0 * * * *" : `0 */${interval} * * *`;
    return interval === 1 ? "* * * * *" : `*/${interval} * * * *`;
  }
  if (
    !/^([01]\d|2[0-3]):[0-5]\d$/.test(choice.time) ||
    (choice.repeat === "custom" &&
      (!choice.days.length ||
        choice.days.some(
          (day) => !Number.isInteger(day) || day < 0 || day > 6,
        ))) ||
    (choice.repeat === "weekly" &&
      (!Number.isInteger(choice.weeklyDay ?? 1) ||
        (choice.weeklyDay ?? 1) < 0 ||
        (choice.weeklyDay ?? 1) > 6))
  )
    return "";
  const [hour, minute] = choice.time.split(":").map(Number);
  const chosenDays = [...new Set(choice.days)].sort((a, b) => a - b);
  const days =
    choice.repeat === "weekdays"
      ? "1,2,3,4,5"
      : choice.repeat === "weekly"
        ? String(choice.weeklyDay ?? 1)
        : choice.repeat === "daily" || chosenDays.length === 7
          ? "*"
          : chosenDays.join(",");
  return `${minute} ${hour} * * ${days}`;
}
export function scheduleDescription(expression: string) {
  const [minute, hour, day, month, weekday] = expression.trim().split(/\s+/);
  if (day !== "*" || month !== "*") return "Custom schedule";
  if (hour === "*" && weekday === "*") {
    if (minute === "*") return "Every minute";
    if (/^\*\/\d+$/.test(minute)) return `Every ${minute.slice(2)} minutes`;
    if (minute === "0") return "Every hour";
  }
  if (minute === "0" && /^\*\/\d+$/.test(hour) && weekday === "*")
    return `Every ${hour.slice(2)} hours`;
  if (!/^\d+$/.test(hour) || !/^\d+$/.test(minute)) return "Custom schedule";
  const clock = `${Number(hour) % 12 || 12}:${minute.padStart(2, "0")} ${Number(hour) >= 12 ? "PM" : "AM"}`;
  if (weekday === "*") return `Every day at ${clock}`;
  if (weekday === "1-5" || weekday === "1,2,3,4,5")
    return `Weekdays at ${clock}`;
  if (/^[0-6]$/.test(weekday))
    return `Every ${weekDays[Number(weekday)]} at ${clock}`;
  if (/^[0-6](?:,[0-6])*$/.test(weekday))
    return `${weekday
      .split(",")
      .map((d) => weekDays[Number(d)].slice(0, 3))
      .join(", ")} at ${clock}`;
  return "Custom schedule";
}
export function SchedulePicker({
  value,
  onChange,
  timezone,
  onTimezoneChange,
}: {
  value: ScheduleChoice;
  onChange: (value: ScheduleChoice) => void;
  timezone: string;
  onTimezoneChange: (value: string) => void;
}) {
  const timeInput = useRef<HTMLInputElement>(null);
  const timed = value.repeat !== "interval";
  const unit = value.intervalUnit || "minutes";
  const cron = scheduleExpression(value);
  return (
    <div className="schedule-picker">
      <div className="schedule-frequency">
        <label className="schedule-frequency-row">
          <span>
            <Repeat2 size={15} /> Repeat
          </span>
          <select
            aria-label="Repeat"
            value={value.repeat}
            onChange={(e) =>
              onChange({
                ...value,
                repeat: e.target.value as ScheduleChoice["repeat"],
              })
            }
          >
            <option value="interval">Interval</option>
            <option value="daily">Daily</option>
            <option value="weekdays">Weekdays</option>
            <option value="weekly">Weekly</option>
            <option value="custom">Custom</option>
          </select>
        </label>
        <label className="schedule-frequency-row">
          <span>
            <Globe2 size={15} /> Timezone
          </span>
          <select
            aria-label="Timezone"
            value={timezone}
            onChange={(e) => onTimezoneChange(e.target.value)}
          >
            <option value="Asia/Kolkata">India (Asia/Kolkata)</option>
            <option value="UTC">UTC</option>
          </select>
        </label>
      </div>
      {value.repeat === "interval" && (
        <div className="monitor-fields schedule-interval">
          <label>
            Check every
            <select
              aria-label="Check every"
              value={value.interval}
              onChange={(e) => onChange({ ...value, interval: e.target.value })}
            >
              {intervals[unit].map((n) => (
                <option value={String(n)} key={n}>
                  {n} {unit === "hours" ? "hour" : "minute"}
                  {n === 1 ? "" : "s"}
                </option>
              ))}
            </select>
          </label>
          <label>
            Unit
            <select
              aria-label="Interval unit"
              value={unit}
              onChange={(event) => {
                const intervalUnit = event.target.value as "minutes" | "hours";
                onChange({
                  ...value,
                  intervalUnit,
                  interval: intervals[intervalUnit].includes(
                    Number(value.interval),
                  )
                    ? value.interval
                    : "1",
                });
              }}
            >
              <option value="minutes">Minutes</option>
              <option value="hours">Hours</option>
            </select>
          </label>
        </div>
      )}
      {value.repeat === "weekly" && (
        <label>
          Day of the week
          <select
            aria-label="Day of the week"
            value={value.weeklyDay ?? 1}
            onChange={(event) =>
              onChange({ ...value, weeklyDay: Number(event.target.value) })
            }
          >
            {[1, 2, 3, 4, 5, 6, 0].map((day) => (
              <option key={day} value={day}>
                {weekDays[day]}
              </option>
            ))}
          </select>
        </label>
      )}
      {timed && (
        <div
          className={`schedule-clock ${value.repeat === "custom" ? "custom-clock" : "preset-clock"}`}
        >
          {value.repeat === "custom" && (
            <p className="custom-clock-heading">
              Custom schedule{" "}
              <span>Choose the time of day and when to repeat.</span>
            </p>
          )}
          <label htmlFor="monitor-time">Time of day</label>
          <div className="schedule-clock-input">
            <input
              ref={timeInput}
              id="monitor-time"
              type="time"
              step="60"
              required
              value={value.time}
              onChange={(e) => onChange({ ...value, time: e.target.value })}
            />
            <button
              type="button"
              aria-label="Choose time"
              title="Choose time"
              onClick={() => {
                try {
                  timeInput.current?.showPicker();
                } catch {
                  timeInput.current?.focus();
                }
              }}
            >
              <Clock3 size={24} />
            </button>
          </div>
          <small>{timezone}</small>
        </div>
      )}
      {value.repeat === "custom" && (
        <fieldset className="schedule-days">
          <legend>Repeat on</legend>
          <div>
            {[1, 2, 3, 4, 5, 6, 0].map((day) => (
              <button
                type="button"
                key={day}
                aria-label={weekDays[day]}
                aria-pressed={value.days.includes(day)}
                onClick={() =>
                  onChange({
                    ...value,
                    days: value.days.includes(day)
                      ? value.days.filter((d) => d !== day)
                      : [...value.days, day],
                  })
                }
              >
                {weekDays[day].slice(0, 3)}
              </button>
            ))}
          </div>
          {!value.days.length && (
            <small role="status">Choose at least one day.</small>
          )}
        </fieldset>
      )}
      <p className="schedule-summary" role="status">
        <Clock3 size={15} />
        {cron
          ? scheduleDescription(cron)
          : "Choose a time and at least one day."}
      </p>
    </div>
  );
}
