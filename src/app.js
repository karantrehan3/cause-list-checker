const webdriver = require("selenium-webdriver"),
  By = webdriver.By;

const driver = new webdriver.Builder().forBrowser("chrome").build();
driver.get("https://highcourtchd.gov.in/clc.php").then(function () {
  driver
    .findElement(By.name("t_f_date"))
    .sendKeys("21/03/2022")
    .then(function () {
      driver.findElement(By.name("button")).click();
    });
});
