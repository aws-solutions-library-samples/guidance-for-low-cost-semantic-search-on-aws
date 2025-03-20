$(document).ready(function () {
    let apiendpoint = apiendpointconfig //from utils.js
    //let cognitoUrl = "XXXXXXXXXXXXXXXXXXXXXXXXXXXX" //placeholder}

    // onclick of the upload button get all the files and show the file names in console 
    $("#prompt-submit").click(function () {
        apiendpoint_upload = $("#apiendpointconfig").text();
        question = $("#prompt-input").val();
        if (!question.trim()) {
            showWarningNotification("Please enter a prompt before submitting", 3000, true);
            return;
        }
        // Show loading notification
        const loadingNotification = showInfoNotification(
            '<i class="fas fa-spinner fa-spin"></i> Saving prompt...', 
            0  // Set duration to 0 to prevent auto-closing
        );
        // console.log(question);
        post({ "system": question }, apiendpoint_upload)
            .then(function (data) {
                // Close loading notification
                closeNotification(loadingNotification);
                
                // Show success notification
                showSuccessNotification("Prompt saved successfully", 3000);
            })
            .catch(function (err) {
                // Close loading notification
                closeNotification(loadingNotification);
                
                // Show error notification
                showErrorNotification("Failed to save prompt: " + err.statusText, 5000);
                console.error(err);
            }
            );
        // alert("Prompt submitted successfully");
    })
    
    $("#tabPrompting").click(function () {
        apiendpoint_upload = $("#apiendpointconfig").text();
        get(apiendpoint_upload + "?prompt=system").then(function (data) {
            // console.log(data);
            $("#prompt-input").val(data["prompt"]);
        });
    })
    
});