import { expect, test } from "vitest";
import {
  scheduleExpression,
  scheduleDescription,
  type ScheduleChoice,
} from "../components/workspace/schedule-picker";

const choice: ScheduleChoice = {
  repeat: "daily",
  time: "09:15",
  days: [0, 1, 2, 3, 4, 5, 6],
  interval: "15",
  intervalUnit: "minutes",
  weeklyDay: 0,
};

test("frequency presets generate the intended days, hours and minutes", () => {
  expect(scheduleExpression(choice)).toBe("15 9 * * *");
  expect(scheduleExpression({ ...choice, repeat: "weekdays" })).toBe(
    "15 9 * * 1,2,3,4,5",
  );
  expect(scheduleExpression({ ...choice, repeat: "weekly" })).toBe(
    "15 9 * * 0",
  );
  expect(scheduleExpression({ ...choice, repeat: "interval" })).toBe(
    "*/15 * * * *",
  );
  expect(
    scheduleExpression({
      ...choice,
      repeat: "interval",
      intervalUnit: "hours",
      interval: "1",
    }),
  ).toBe("0 * * * *");
  expect(
    scheduleExpression({
      ...choice,
      repeat: "interval",
      intervalUnit: "hours",
      interval: "6",
    }),
  ).toBe("0 */6 * * *");
});

test("custom time supports midnight, selected days, all days and rejects incomplete choices", () => {
  expect(
    scheduleExpression({
      ...choice,
      repeat: "custom",
      time: "00:05",
      days: [5, 1, 3, 3],
    }),
  ).toBe("5 0 * * 1,3,5");
  expect(
    scheduleExpression({ ...choice, repeat: "custom", time: "23:59" }),
  ).toBe("59 23 * * *");
  for (const invalid of [
    { repeat: "custom", days: [] },
    { repeat: "custom", days: [7] },
    { repeat: "weekly", weeklyDay: -1 },
    { time: "24:30" },
    { repeat: "interval", intervalUnit: "hours", interval: "15" },
    { repeat: "interval", interval: "0" },
  ] as Partial<ScheduleChoice>[])
    expect(scheduleExpression({ ...choice, ...invalid })).toBe("");
});

test("saved schedules retain human-readable frequency and time descriptions", () => {
  expect(scheduleDescription("15 9 * * 1,2,3,4,5")).toBe("Weekdays at 9:15 AM");
  expect(scheduleDescription("15 9 * * 1-5")).toBe("Weekdays at 9:15 AM");
  expect(scheduleDescription("20 17 * * 0")).toBe("Every Sunday at 5:20 PM");
  expect(scheduleDescription("5 0 * * 1,3,5")).toBe(
    "Mon, Wed, Fri at 12:05 AM",
  );
  expect(scheduleDescription("0 */6 * * *")).toBe("Every 6 hours");
});
